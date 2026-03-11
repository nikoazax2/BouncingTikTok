"""Sound generation for bounce events and music assembly."""

import math
import wave
import os
import tempfile
import numpy as np

EVENT_MUSIC = "music"
EVENT_DEATH = "death"


def midi_to_freq(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def generate_synth_lead(freq: float, duration: float = 0.8, sample_rate: int = 44100, volume: float = 0.6) -> np.ndarray:
    """Generate a futuristic synth lead note - sawtooth + square with filter sweep and detune."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Detuned sawtooth oscillators (fat analog sound)
    detune = 1.005
    saw1 = 2.0 * (t * freq % 1.0) - 1.0
    saw2 = 2.0 * (t * freq * detune % 1.0) - 1.0
    saw3 = 2.0 * (t * freq / detune % 1.0) - 1.0
    # Sub oscillator (square, one octave down)
    sub = np.sign(np.sin(2 * np.pi * freq * 0.5 * t)) * 0.3
    # Mix
    wave_data = (saw1 + saw2 + saw3) * 0.3 + sub
    # LPF sweep: simulate with harmonic rolloff over time
    cutoff_env = np.clip(4.0 * np.exp(-t * 3.0) + 0.5, 0.5, 5.0)
    # Apply simple smoothing as pseudo-filter (moving average scaled by cutoff)
    filter_size = np.clip((1.0 / cutoff_env) * 20, 1, 80).astype(int)
    filtered = np.copy(wave_data)
    for i in range(1, len(t)):
        k = filter_size[i]
        start = max(0, i - k)
        filtered[i] = np.mean(wave_data[start:i + 1])
    wave_data = filtered
    # Envelope: snappy attack, medium sustain, smooth release
    attack = 1 - np.exp(-t * 800)
    sustain = 0.7 + 0.3 * np.exp(-t * 2.0)
    release_start = duration * 0.7
    release = np.where(t > release_start, np.exp(-(t - release_start) * 8), 1.0)
    envelope = attack * sustain * release
    wave_data = wave_data * envelope * volume
    return wave_data


def generate_death_sound(duration: float = 0.4, sample_rate: int = 44100, volume: float = 0.6) -> np.ndarray:
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    freq = 400 - 320 * (t / duration)
    phase = np.cumsum(2 * np.pi * freq / sample_rate)
    wave_data = np.sign(np.sin(phase)) * 0.4 + np.sin(phase * 1.5) * 0.3 + np.sin(phase * 0.5) * 0.2
    np.random.seed(42)
    wave_data += np.random.uniform(-0.1, 0.1, len(t))
    envelope = np.exp(-t * 5) * (1 - np.exp(-t * 300))
    wave_data = wave_data * envelope * volume
    return wave_data


def extract_notes_from_midi(midi_path: str, channel: int | None = None,
                            filter_channels: list[int] | None = None) -> list:
    """Extract note-on MIDI note numbers.

    Args:
        midi_path: path to MIDI file
        channel: single MIDI channel (0-indexed), or None for chord mode.
        filter_channels: list of channels to include (None = all).
    """
    import mido
    mid = mido.MidiFile(midi_path)
    if channel is not None:
        notes = []
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'note_on' and msg.velocity > 0 and msg.channel == channel:
                    notes.append(msg.note)
        return notes
    # Chord mode: collect timed notes with channel info
    timed = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                if filter_channels is None or msg.channel in filter_channels:
                    timed.append((t, msg.note, msg.channel))
    timed.sort(key=lambda x: x[0])
    if not timed:
        return []
    # Group notes within 10 ticks of each other as chords
    chords = []
    cur_time = timed[0][0]
    cur_chord = [{"n": timed[0][1], "ch": timed[0][2]}]
    for t, note, ch in timed[1:]:
        if t - cur_time <= 10:
            cur_chord.append({"n": note, "ch": ch})
        else:
            chords.append(cur_chord)
            cur_time = t
            cur_chord = [{"n": note, "ch": ch}]
    chords.append(cur_chord)
    return chords


def create_bounce_soundtrack(bounce_events: list[tuple[float, str]], total_duration: float,
                             note_sequence: list[int], sample_rate: int = 44100,
                             music_path: str | None = None, midi_path: str | None = None,
                             chunk_ms: int = 500,
                             filter_channels: list[int] | None = None) -> str:
    """Create a WAV file with bounce sounds at specified times.

    Priority: MIDI file > MP3 chunks > synthetic notes.
    """
    total_samples = int(sample_rate * total_duration)
    audio = np.zeros(total_samples)

    sorted_events = sorted(bounce_events)
    death_sound = generate_death_sound(sample_rate=sample_rate)

    # Determine note source
    midi_notes = None
    music_data = None

    if midi_path and os.path.exists(midi_path):
        print(f"  Loading MIDI: {midi_path}")
        midi_notes = extract_notes_from_midi(midi_path, filter_channels=filter_channels)
        print(f"  Found {len(midi_notes)} notes in MIDI")
    elif music_path and os.path.exists(music_path):
        print(f"  Loading music: {music_path}")
        import subprocess as _sp
        raw_pcm = _sp.run([
            "ffmpeg", "-i", music_path, "-f", "s16le", "-ac", "1",
            "-ar", str(sample_rate), "pipe:1",
        ], capture_output=True).stdout
        music_data = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float64) / 32768.0

    note_idx = 0
    music_cursor = 0
    chunk_samples = int(sample_rate * chunk_ms / 1000)

    for t, event_type in sorted_events:
        start_out = int(t * sample_rate)
        if start_out >= total_samples:
            continue

        if event_type == EVENT_DEATH:
            end_out = min(start_out + len(death_sound), total_samples)
            audio[start_out:end_out] += death_sound[:end_out - start_out]
        else:
            if midi_notes is not None:
                chord = midi_notes[note_idx % len(midi_notes)]
                note_idx += 1
                # chord can be int, or list of ints, or list of dicts with "n" key
                if isinstance(chord, (int, float)):
                    notes_to_play = [int(chord)]
                elif isinstance(chord, list):
                    notes_to_play = [item["n"] if isinstance(item, dict) else int(item) for item in chord]
                else:
                    notes_to_play = [60]
                for midi_note in notes_to_play:
                    freq = midi_to_freq(midi_note)
                    tone = generate_synth_lead(freq, duration=0.5, sample_rate=sample_rate, volume=0.6 / max(1, len(notes_to_play)))
                    end_out = min(start_out + len(tone), total_samples)
                    audio[start_out:end_out] += tone[:end_out - start_out]
            elif music_data is not None:
                start_music = music_cursor
                end_music = start_music + chunk_samples
                if start_music >= len(music_data):
                    music_cursor = 0
                    start_music = 0
                    end_music = chunk_samples
                chunk = music_data[start_music:end_music].copy()
                music_cursor = end_music
                fade_len = min(int(sample_rate * 0.01), len(chunk) // 4)
                if fade_len > 0 and len(chunk) > fade_len * 2:
                    chunk[:fade_len] *= np.linspace(0, 1, fade_len)
                    chunk[-fade_len:] *= np.linspace(1, 0, fade_len)
                end_out = min(start_out + len(chunk), total_samples)
                audio[start_out:end_out] += chunk[:end_out - start_out]
            else:
                # Fallback: synthetic notes from config sequence
                freq = midi_to_freq(note_sequence[note_idx % len(note_sequence)])
                note_idx += 1
                tone = generate_synth_lead(freq, duration=0.5, sample_rate=sample_rate, volume=0.5)
                end_out = min(start_out + len(tone), total_samples)
                audio[start_out:end_out] += tone[:end_out - start_out]

    # Normalize
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * 0.85

    audio_int = (audio * 32767).astype(np.int16)

    tmp_path = os.path.join(tempfile.gettempdir(), "bounce_soundtrack.wav")
    with wave.open(tmp_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int.tobytes())

    return tmp_path
