# a fastapi server for the api.
# this app is used to configure a custom music creation algorithm.
# the algorithm maps the user's input sound to a song.
# the songs are midi files, the user's input is an audio file.

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from starlette.responses import RedirectResponse, FileResponse, Response

from pretty_midi import PrettyMIDI
import soundfile as sf

from effects import Sound
from songstitch import SongStitcher
import cloud

import os
import glob
import shortuuid
import sys
import gc
import io
import traceback

# Logic
def get_midi_name(midi_path):
    return midi_path.split("/")[-1].split(".")[0]


def valid_audio(file: UploadFile):
    return "audio" in file.content_type


# globals
STORAGE_BUCKET = "bazamjam.appspot.com"

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

# if not os.path.isdir('midi/'): os.mkdir('midi/')
# if not os.path.isdir('out/'): os.mkdir('out/')

# app.mount("/out", StaticFiles(directory="out"), name="out")

# routes
print(f"app size: {sys.getsizeof(app)/1000000}MB")
print(f"midi size: {sys.getsizeof(_midis)/1000000}MB")
print(f"song size: {sys.getsizeof(_songs)/1000000}MB")


@app.get("/")
async def root():
    return RedirectResponse("/docs")


@app.get("/get_songs")
async def get_songs():
    return _songs


@app.get("/get_instruments")
async def get_instruments(song_id):
    if song_id not in _midis.keys():
        print(_midis.keys())
        return {"error": "song not found"}

    return {
        num: instrument.name
        for num, instrument in enumerate(_midis[song_id].instruments)
    }


# TODO: limit file size
@app.post("/create_song")
async def create_song(
    response: Response,
    song_id: str,
    instrument_num: int,
    key_shift: int,
    user_sample: UploadFile = File(...),
    all_tracks: bool = False,
    map_drums: bool = False,
):
    response.headers["Access-Control-Allow-Origin"] = "*"
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

    # TODO: move most of this logic into songstitch

    try:
        # choose which instruments to map the sound to
        all_instrs = list(range(len(midi.instruments)))
        instruments_to_map = all_instrs if all_tracks else [instrument_num]
        unmapped_instruments = set(all_instrs) - set(instruments_to_map)

        # if not map_drums:
        #     print("no drums")
        #     instruments_to_map = filter(lambda idx: midi.instruments[idx].is_drum==False, instruments_to_map)
        #     print(len(all_instrs) - len(list(instruments_to_map)), "drums removed")

        # map the sound to those instruments
        stitcher = SongStitcher(midi, sound.fs)
        joined_mapped_track = np.zeros(0)
        for instrument in instruments_to_map:
            mapped_instr_audio = stitcher.map_sound(sound, instrument, key_shift)
            if mapped_instr_audio is None:
                raise Exception("Song not created")
            else:
                oldlen = len(joined_mapped_track)
                joined_mapped_track = SongStitcher.join_tracks(
                    [joined_mapped_track, mapped_instr_audio]
                )
                print(f"len: {oldlen} -> {len(joined_mapped_track)}")
        gc.collect()
        print(f"map traccked size: {joined_mapped_track.nbytes/1000000} MB")

        unmapped_tracks = stitcher.get_synths(exclude=instruments_to_map)

        print("unmapped tracks size:", unmapped_tracks.nbytes / 1000000, "MB")

        synth_song = SongStitcher.join_tracks([joined_mapped_track, unmapped_tracks])
        print("synth song size:", sys.getsizeof(synth_song) / 1000000, "MB")
        del unmapped_tracks
        del joined_mapped_track
        gc.collect()

        # store the end result song
        format = "flac"
        name = f"{_songs[song_id]}_i{instrument_num}_k{key_shift}_{shortuuid.random(8)}.{format}"
        print(f"name: {name}")

        # google cloud upload
        file = io.BytesIO()
        sf.write(file, synth_song, sound.fs, format=format)
        print("virtual file:", file.getbuffer().nbytes / 1000000, "MB")
        blobl_url = cloud.upload_blob(STORAGE_BUCKET, file.getbuffer().tobytes(), name)
    except Exception as e:
        traceback.print_exc()
        msg = "Error creating song: " + str(e)
        return HTTPException(
            status_code=500, detail=msg, headers={"Access-Control-Allow-Origin": "*"}
        )
    gc.collect()
    return {"song": blobl_url}


# donwloads a users outputted song. currently the song_id is the file path
@app.get("/download_song")
async def download_song(song_id: str):
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


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    import numpy as np

    arr = np.random.random(100000).tobytes()
    print(f"upload size: {sys.getsizeof(file)/1000000}MB")
    return cloud.upload_blob(STORAGE_BUCKET, arr, file.filename)


def download(file_path):
    """
    Download file for given path.
    """
    if os.path.isfile(file_path):
        return FileResponse(file_path)
        # return FileResponse(path=file_path)
    return None
