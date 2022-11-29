Witness Angel Recorder
######################################

This is a cross-platform software suite for Witness Angel devices relying on Python language.

It allows recording data (from RTSP streams, for Raspberry Pi camera/mic...) in a "write-only" fashion,
using Flightbox cryptosystem. Thus, any data can be continuously recorded, but only the agreement of a sufficient number of trusted third parties (called "trustees" or "key guardians") will allow to decrypt some recordings.

The application also features interfaces to manage foreign trusted third parties, to manage stored containers, and to attempt decryption operations on them.

Related solution homepages:

- https://witnessangel.com/en/videotestimony-for-condominiums/
- https://witnessangel.com/en/witness-angel-handbag/


Setup
---------------

- Install a recent "ffmpeg" executable somewhere on your system PATH
- Install all dependencies using Poetry, and add "Pyobjus" package with pip if you're on OSX
- Launch "python main.py" for the GUI app and its recorder service, or "python main.py --service" for the recorder service only

To generate a standalone version of the program::

    $ pip install pyinstaller
    $ python -m PyInstaller pyinstaller.spec

    Note that arguments like "--windowed --onefile" are overridden by the content of the spec file
