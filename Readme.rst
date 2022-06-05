Witness Angel Ward (NVR System)
#################################


This is a proof-of-concept application of Network Video Recording, using Flightbox cryptosystem to secure recorded data in a "write-only" fashion.

RTSP streams can be recorded autonomously, but only the agreement of a sufficient number of trusted third parties (called "trustees" or "key guardians") will allow to decrypt some records.


Setup
---------------

- Install a recent "ffmpeg" executable somewhere on your system PATH
- Install all dependencies using Poetry, and add "Pyobjus" package with pip if you're on OSX
- Launch "main.py"

