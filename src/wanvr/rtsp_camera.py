import subprocess
import threading

from datetime import timezone, datetime
from kivy.logger import Logger as logger

from wacryptolib.sensor import TarfileRecordsAggregator
from wacryptolib.utilities import PeriodicTaskHandler, synchronized, get_utc_now_date

import io


class PeriodicStreamPusher(PeriodicTaskHandler):
    """
    This class launches an external sensor, and periodically pushes thecollected data
    to a tarfile aggregator.
    """

    _current_start_time = None

    # Fields to be overridden
    sensor_name = None
    record_extension = None

    def __init__(self,
                 interval_s: float,
                 tarfile_aggregator: TarfileRecordsAggregator):
        super().__init__(interval_s=interval_s, runonstart=False)
        self._tarfile_aggregator = tarfile_aggregator
        assert self.sensor_name, self.sensor_name
        #self._lock = threading.Lock() ??

    @synchronized
    def start(self):
        """
        FR : Methode qui permet de ne pas redémarrer une deuxième fois l'enregistrement'

        """
        super().start()

        logger.info(">>> Starting sensor %s" % self)

        self._do_start_recording()

        logger.info(">>> Starting sensor %s" % self)

    def _do_start_recording(self):
        raise NotImplementedError("%s -> _do_start_recording" % self.sensor_name)

    @synchronized
    def stop(self):
        super().stop()

        logger.info(">>> Starting sensor %s" % self)

        from_datetime = self._current_start_time
        to_datetime = get_utc_now_date()

        data = self._do_stop_recording()

        self._do_push_buffer_file_to_aggregator(data=data, from_datetime=from_datetime, to_datetime=to_datetime)

        logger.info(">>> Starting sensor %s" % self)

    def _do_stop_recording(self):
        raise NotImplementedError("%s -> _do_stop_recording" % self.sensor_name)

    def _do_push_buffer_file_to_aggregator(self, data, from_datetime, to_datetime):

        assert from_datetime and to_datetime, (from_datetime, to_datetime)

        self._tarfile_aggregator.add_record(
            sensor_name=self.sensor_name,
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            extension=self.file_extension,
            data=data,
        )

    @synchronized
    def _offloaded_run_task(self):

        if not self.is_running:
            return

        from_datetime = self._current_start_time
        to_datetime = datetime.now(tz=timezone.utc)

        data = self._do_stop_recording() # Renames target files
        self._do_start_recording()  # Must be restarded imediately

        self._do_push_buffer_file_to_aggregator(data=data, from_datetime=from_datetime, to_datetime=to_datetime)




class RtspCameraSensor(PeriodicStreamPusher):

    def __init__(self,
                 interval_s,
                 tarfile_aggregator,
                 video_stream_url):
        super().__init__(interval_s=interval_s, tarfile_aggregator=tarfile_aggregator)

        self._video_stream_url = video_stream_url

    def _launch_and_wait_ffmpeg_process(self):

        exec = [
            "ffmpeg",
            "-y",  # Always say yes to questions
            "-rtsp_transport",
            "tcp"]
        codec = [
            "-vcodec",
            "copy",
            "-acodec",
            "copy",
            "-map",
            "0"]
        logs = [
            "-loglevel",
            "warning"
        ]
        output = [
            "pipe:1"  # Pipe to stdout
        ]

        pipeline = exec + self.input + codec + self.recording_duration + self.format_params + logs + output

        logger.info("Calling RtspCameraSensor subprocess command: {}".format(" ".join(pipeline)))
        self._subprocess = subprocess.Popen(pipeline,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=None)  # Stderr is left floating for now

        self._stdout_buff = []
        self._stdout_thread = threading.Thread(target=self._subprocess._readerthread,
                                                args=(self._subprocess.stdout, self._stdout_buff))


        #returncode = self.process.wait()
        #if returncode:
        #    logger.warning("recorder process exited with abnormal code %s", returncode)

    def _do_start_recording(self):
        self._launch_and_wait_ffmpeg_process()

    def _do_stop_recording(self):
        self._subprocess.stdin.write("q")  # FFMPEG command to quit
        self._stdout_thread.join(timeout=10)
        return self._stdout_buff[0] if self._stdout_buff else b""


'''
class CameraSensor(PeriodicStreamPusher):

    camera = None

    RESOLUTIONS = {'low' : (640, 480),
                   'medium' : (1280, 720),
                   'high' : (1920, 1080)}

    FRAMERATE = {'30' : 30,
                 '60' : 60,
                 '90' : 90} # Nombre d'image par seconde (High ne peut que avoir 30fps, Seul Low peut avoir 90fps)

    #_current_start_time = None

    def __init__(self,
                 interval_s: float,
                 tarfile_aggregator: TarfileRecordsAggregator,
                 resolution:tuple = RESOLUTIONS['medium'],
                 framerate:int = FRAMERATE['30']):
        """
        FR : Initialisation des variables d'instances interval_s et
        tarfile_agregator contenue dans la classe TarfileRecordsAggregator
        """
        super().__init__(interval_s=interval_s, tarfile_aggregator=tarfile_aggregator)
        self._current_buffer = io.BytesIO()
        self._resolution = resolution
        self._framerate = framerate


    def _do_start_recording(self):
        """
        FR : Methode qui permet à la camera de la Raspberry de
        commencer à enregistrer des videos

        """
        camera = self.camera

        if not camera:
        	camera = picamera.PiCamera(camera_num=0, stereo_mode='none', stereo_decimate=False, resolution=self._resolution, framerate=self._framerate, sensor_mode=0, led_pin=None)
        	self.camera = camera

       	camera.start_recording(self._current_buffer, format='h264', quality=23)

        camera.wait_recording(5)

        self._current_start_time = datetime.now(tz=timezone.utc) # TODO make datetime utility with TZ

        return camera


    def _do_capture_preview(self):
        """
        FR : Methode qui permet de prendre une capture photo
        sans interrompre l'enregistrement video

        """
        self.camera.capture('test.jpg', use_video_port=True)


    def _do_stop_recording(self):
        """
        FR : Methode qui permet à la camera de la Raspberry de
        stopper l'enregistrement video

        """
        self.camera.stop_recording()

        _old_buffer = self._current_buffer

        self._current_buffer = io.BytesIO()

        self._current_start_time = None

        return _old_buffer.getbuffer()


    def get_camera_sensor(interval_s, tarfile_aggregator):
        """
        FR : Getter qui permet de récupérer les valeurs des variables interval_s et
        tarfile_aggregator

        """
        return CameraSensor(interval_s=interval_s, tarfile_aggregator=tarfile_aggregator)

if __name__ == '__main__' :

   obj = CameraSensor(5, None )
   obj._do_start_recording()
   obj._do_capture_preview()
   obj._do_stop_recording()
   obj._offloaded_run_task()
   #obj._do_push_buffer_file_to_aggregator(None, 0, 0)
'''
