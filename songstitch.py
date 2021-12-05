#%%
import functools
from effects import Sound
import numpy as np
import pandas as pd
import pretty_midi
from itertools import accumulate

# takes in sound and midi and outputs a SONDified midi song
# todo: add suport for possible:
# 	mapping multiple sounds to mulitple instruments
# 	different methods for splicing in sounds
# 	joining instruments into one df
# 	shifting keys
# 	synthesize rest of instruments, add on tops


class SongStitcher:
    def __init__(
        self,
        midi,
        fs=None,
    ):
        self.midi = midi
        self.fs = fs

    # Read MIDI and extract instrument
    def extract_song_data(midi_data, midi_instrument: int, key_shift: float):
        # instrument to map the sounds to
        mapping_instrument = midi_data.instruments[midi_instrument]
        mapping_instrument.remove_invalid_notes()

        # Form an array of the song parameters in question
        attrs = ["start", "end", "pitch", "velocity"]
        song_data = [
            [getattr(note, a) for a in attrs] for note in mapping_instrument.notes
        ]

        # Turn that array into a dataframe
        song_df = pd.DataFrame(song_data, columns=["start", "end", "note", "velocity"])

        # Extract frequency information
        to_hz = lambda notenum: 2 ** ((notenum + key_shift - 69) / 12) * 440
        song_df["freq"] = song_df.note.map(to_hz)

        # Calculate note duration
        song_df["duration"] = song_df.end - song_df.start
        song_df["round_duration"] = song_df.duration.apply(lambda v: np.round(v, 2))

        # remove empty notes
        song_df = song_df[song_df.round_duration != 0]

        return song_df

    # returns a list of synthesized instruments
    def get_synths(self, exclude=[], fs=None) -> list:
        # Parse inputs
        if not self.fs or fs:
            raise Exception("must specify sampling rate")
        fs = fs if fs else self.fs

        # get all our tracks
        joined_track = np.zeros(0)
        for i, instr in enumerate(self.midi.instruments):
            if i not in exclude:
                print(i)
                joined_track = SongStitcher.join_tracks([joined_track, instr.synthesize(fs)])

        # process
        if len(joined_track) > 0:
            joined_track /= np.max(joined_track)  # normalize sound
            joined_track *= 50 / 100  # volumes

        return joined_track

    # joins a list of tracks into a single track (sums them)
    def join_tracks(tracks: list) -> np.ndarray:
        # pad them to all the same length
        max_length = max(len(row) for row in tracks)
        pad_equal = lambda arr: np.pad(arr, (0, max_length - len(arr)))
        tracks = map(pad_equal, tracks)

        # join them
        return np.array(list(tracks)).sum(axis=0)

    # TODO: What if you did like a sliding pitch shift so each sound is the same length
    # 		instead of having short and fast versions of the sosund. you could overlay multiple
    # 		different copies too when there's >1 note playing at once.
    # 		you could also still just calculate the shift K times for K different frequencies in the song.
    # 		you just have to chop the sound in the right place and stitch it with a different freq sound.
    # 		prolly a clever way to deal with rests too. like continuing from where you left off
    def map_sound(self, sound, midi_instrument, key_shift=0):
        song_df = SongStitcher.extract_song_data(self.midi, midi_instrument, key_shift)
        fs = sound.fs if not self.fs else self.fs

        # create empty samples array for the output song
        song_length = song_df.end.iloc[-1] + 3
        total_samples = int(np.ceil(song_length * fs))
        out_song = np.zeros((total_samples,), dtype=sound.y.dtype)

        # generate a sound for each pitch/duration note present in the song
        freq_groups = song_df.groupby(by=["freq"])["round_duration"]
        sounds = dict()
        for freq, durations in freq_groups:
            # generate the base pitch shifted
            freq_shifted = sound.pitch_shift_to(freq)
            for t in set(durations):
                if t == 0:
                    print(midi_instrument, t)
                    continue
                # Generate a sound for each duration present at that pitch
                rate = sound.duration / t
                sounds[(freq, t)] = Sound.time_stretch(
                    freq_shifted, rate
                )  # todo: sound tretch then pitch shift?

        # place each sound into the output array, corresponding with the notes
        for _, row in song_df.iterrows():
            # Gather note data and get the sound
            cur_sound = sounds[(row["freq"], row["round_duration"])]
            start_sample = int(row["start"] * sound.fs)
            end_sample = start_sample + len(cur_sound)

            # Place it in the output
            if end_sample < len(out_song):
                out_song[start_sample:end_sample] += cur_sound
            else:
                # Adjust for sounds rolling over the total song length
                end_sample = len(out_song)
                out_song[start_sample:end_sample] += cur_sound[
                    : end_sample - start_sample
                ]
                break

        return out_song


# # %%
# import os
# dir_path = os.path.dirname(os.path.realpath(__file__))
# file_path = os.path.join(dir_path, "sounds/yowl2.wav")
# sound = Sound(path=file_path, trim=False)

# sound.estimate_f0()
# #%%
# ss = SongSticher('songs/piano_man.mid', sound, key_shift=0)
# sitched_song = ss.map_sound()
# # sitched_song,i = ss.map_sound_2()

# print("song mapped")
# #%%
# idxs = pd.Series(i)
# idxs[:sound.fs*3].plot(xlabel='out samples', ylabel='input sound samples')
# # plt.xlabel('samples')
# #%%
# idxs = pd.Series(sitched_song)
# idxs[:sound.fs*3].plot()
# #%%
# import sounddevice as sd
# start, length = 0,10
# segment = sitched_song[sound.fs*start:sound.fs*(start+length)]
# sd.play(segment, sound.fs)
# import time
# time.sleep(length)
# print("done")

# #%%

# import soundfile as sf
# sf.write('out/gunner_man.wav', sitched_song, sound.fs, subtype='PCM_24')
# print('dun wrote')
# %%


# TODO: what if you took it a step farther and approximated f0 for each window of a real mp3/song and then
# 		tuned the audio to that window

# TODO: be able to select which instrument you want to map ur voice onto
# 		and map multiple voices to different instruments
