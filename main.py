# a fastapi server for the api.
# this app is used to configure a custom music creation algorithm.
# the algorithm maps the user's input sound to a song.
# the songs are midi files, the user's input is an audio file.

from fastapi import FastAPI, UploadFile, File
import numpy as np
from pretty_midi import PrettyMIDI
import soundfile as sf
from effects import Sound

from songstitch import SongSticher
import glob
import shortuuid

# Logic

def get_midi_name(midi_path):
    return midi_path.split('/')[-1].split('.')[0]


def valid_audio(file: UploadFile):
    return 'audio' in file.content_type

# globals


# song id = midi song name
_midis = {get_midi_name(f):PrettyMIDI(f) for f in glob.glob('midi/*.mid')}
app = FastAPI()

# routes

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get('/get_songs')
def get_songs():
    return {i:k for i,k in enumerate(_midis.keys())}

@app.get('/get_instruments')
def get_instruments(song_id):
    return {i:instrument.name for i,instrument in enumerate(_midis[song_id].instruments)}

@app.post('/create_song')
async def create_song(song_id: str, instrument_num: int, key_shift: int, user_sample: UploadFile = File(...)):
    try:
        if song_id in _midis:
            midi = _midis[song_id]
        else:
            raise Exception('Invalid song id')
        
        if valid_audio(user_sample):
            sound = Sound(path=user_sample.file, trim=False)        
        else:
            raise Exception('Invalid audio file')
        
        if instrument_num < 0 or instrument_num >= len(midi.instruments):
            raise Exception('Invalid instrument number')
        
        if key_shift not in range(-84,84):
            key_shift = 0

        stitcher = SongSticher(midi,sound.fs)
        song = stitcher.map_sound(sound, instrument_num, key_shift)
        if song is None:
            raise Exception('Song not created')

        name = f'{song_id}_{instrument_num}_{key_shift}_{shortuuid.random(8)}.wav'
        # sf.write(f'out/{name}', song, sound.fs, subtype='PCM_24')
        
        tracks = stitcher.get_synths([instrument_num])
        synth_song = SongSticher.join_tracks(tracks + [song])

        sf.write(f'out/synth_{name}', synth_song, sound.fs, subtype='PCM_24')
        print("wrote other song too")
    except Exception as e:
        print(e)
        return {'error': str(e)}

    return {'song': name}


