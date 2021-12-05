# a fastapi server for the api.
# this app is used to configure a custom music creation algorithm.
# the algorithm maps the user's input sound to a song.
# the songs are midi files, the user's input is an audio file.

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, FileResponse

from pretty_midi import PrettyMIDI
import soundfile as sf

from effects import Sound
from songstitch import SongSticher

import os
import glob
import shortuuid

# Logic
def get_midi_name(midi_path):
    return midi_path.split("/")[-1].split(".")[0]


def valid_audio(file: UploadFile):
    return "audio" in file.content_type


# globals


# song id = midi song name
_songs = {}
_midis = {}
for id, f in enumerate(glob.glob("midi/*.mid")):
    id = str(id)
    _songs[id] = get_midi_name(f)
    _midis[id] = PrettyMIDI(f)
    

# app configuration
app = FastAPI()

# TODO: Make this more restrictive
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/out", StaticFiles(directory="out"), name="out")

# routes


@app.get("/")
async def root():
    return RedirectResponse("/docs")


@app.get("/get_songs")
def get_songs():
    return _songs


@app.get("/get_instruments")
def get_instruments(song_id):
    if song_id not in _midis.keys():
        print(_midis.keys())
        return {"error": "song not found"}
    
    return {
        num: instrument.name for num, instrument in enumerate(_midis[song_id].instruments)
    }


@app.post("/create_song")
async def create_song(
    song_id: str,
    instrument_num: int,
    key_shift: int,
    user_sample: UploadFile = File(...),
    all_tracks: bool = False,
    map_drums: bool = False,
):
    print("start")
    if song_id in _songs:
        midi = _midis[song_id]
    else:
        raise Exception("Invalid song id")

    if valid_audio(user_sample):
        sound = Sound(path=user_sample.file, trim=False)
    else:
        raise Exception("Invalid audio file")

    if not all_tracks and (
        instrument_num < 0 or instrument_num >= len(midi.instruments)
    ):
        raise Exception("Invalid instrument number")

    if key_shift not in range(-84, 84):
        key_shift = 0

    # choose which instruments to map the sound to
    all_instrs = list(range(len(midi.instruments)))
    instruments_to_map = all_instrs if all_tracks else [instrument_num]
    unmapped_instruments = set(all_instrs) - set(instruments_to_map)

    # if not map_drums:
    #     print("no drums")
    #     instruments_to_map = filter(lambda idx: midi.instruments[idx].is_drum==False, instruments_to_map)
    #     print(len(all_instrs) - len(list(instruments_to_map)), "drums removed")

    # map the sound to those instruments
    stitcher = SongSticher(midi, sound.fs)
    mapped_tracks = []
    for instrument in instruments_to_map:
        mapped_instr_audio = stitcher.map_sound(sound, instrument, key_shift)
        if mapped_instr_audio is None:
            raise Exception("Song not created")
        else:
            mapped_tracks += [mapped_instr_audio]

    unmapped_tracks = stitcher.get_synths(exclude=instruments_to_map)
    synth_song = SongSticher.join_tracks(mapped_tracks + unmapped_tracks)

    # store the end result song
    name = f"{song_id}_{instrument_num}_{key_shift}_{shortuuid.random(8)}.wav"
    filepath = f"out/synth_{name}"
    sf.write(filepath, synth_song, sound.fs, subtype="PCM_24")

    print("wrote other song too")

    return {"song": filepath}


# donwloads a users outputted song. currently the song_id is the file path
@app.get("/download_song")
def download_song(song_id: str):
    # validate id
    if (
        not song_id.startswith("out/")
        or not os.path.isfile(song_id)
        or not song_id.endswith(".wav")
    ):
        return {"error": "invalid song id"}

    # return song
    song_path = song_id
    return FileResponse(song_path, media_type="audio/wav")


def download(file_path):
    """
    Download file for given path.
    """
    if os.path.isfile(file_path):
        return FileResponse(file_path)
        # return FileResponse(path=file_path)
    return None
