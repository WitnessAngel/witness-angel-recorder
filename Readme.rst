Witness Angel Network Video recorder
######################################

Application homepage: https://witnessangel.com/en/videotestimony-for-condominiums/

This is a proof-of-concept application of Network Video Recording, using Flightbox cryptosystem to secure recorded data in a "write-only" fashion.

thus, RTSP streams can be recorded continuously, but only the agreement of a sufficient number of trusted third parties (called "trustees" or "key guardians") will allow to decrypt some recordings.


Setup
---------------

- Install a recent "ffmpeg" executable somewhere on your system PATH
- Install all dependencies using Poetry, and add "Pyobjus" package with pip if you're on OSX
- Launch "python main.py" for the GUI and its recorder service, or "python main.py --service" for the recorder service only

To generate a standalone version of the program::

    $ pip install pyinstaller
    $ python -m PyInstaller pyinstaller.spec

    Note that arguments like "--windowed --onefile" are overridden by the content of the spec file
