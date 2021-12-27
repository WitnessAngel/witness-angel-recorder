Witness Angel Ward (NVR System)
#################################


This is a proof-of-concept application of Network Video Recording, using Flightbox cryptosystem to secure recorded data
in a "write-only" fashion.

RTSP streams can be recorded autonomously, but only the agreement of a sufficient number of trusted third parties
(called "escrows") will allow to decrypt some records.


Setup
---------------

- Install a recent "ffmpeg" executable somewhere on your system PATH
- Install this package and launch "wanvr"


Workflow
----------------

- Each escrow creates an authentication USB key using the W.A "keygen" project, protected by a passphrase
- Each authentication USB key gets registered near the NVR application
- When recording is launched, RTSP records are immediately encrypted into Flightbox cryptainers
- Decrypting some cryptainers required enough escrows to enter their passphrase




rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov
