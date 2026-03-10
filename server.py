"""Web GUI server for BouncingTikTok."""

import os
import sys
from flask import Flask, send_from_directory, request, jsonify

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWED_ORIGINS = [
    "https://bouncing-tik-tok.vercel.app",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "https://217-154-121-187.sslip.io",
]

app = Flask(__name__, static_folder=PROJECT_DIR, static_url_path="/static")


@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/")
def index():
    return send_from_directory(PROJECT_DIR, "web.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(PROJECT_DIR, filename)


_current_midi = None  # path to current MIDI file


def _get_midi_path():
    if _current_midi and os.path.exists(_current_midi):
        return _current_midi
    import glob
    mid_files = glob.glob(os.path.join(PROJECT_DIR, "*.mid")) + \
                glob.glob(os.path.join(PROJECT_DIR, "*.midi"))
    return mid_files[0] if mid_files else None


@app.route("/api/midi-upload", methods=["POST"])
def midi_upload():
    global _current_midi
    import mido
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "Aucun fichier"}), 400
    dest = os.path.join(PROJECT_DIR, "uploaded.mid")
    f.save(dest)
    _current_midi = dest
    return _midi_info(dest)


@app.route("/api/midi-info")
def midi_info():
    path = _get_midi_path()
    if not path:
        return jsonify({"tracks": [], "filename": ""})
    return _midi_info(path)


def _midi_info(path):
    import mido
    GM_INSTRUMENTS = [
        "Piano acoustique","Piano brillant","Piano electrique","Honky-tonk","Piano Rhodes",
        "Piano chorus","Clavecin","Clavinet","Celesta","Glockenspiel","Boite a musique",
        "Vibraphone","Marimba","Xylophone","Cloches tubulaires","Dulcimer","Orgue Hammond",
        "Orgue percussif","Orgue rock","Orgue d'eglise","Harmonium","Accordeon","Harmonica",
        "Bandoneon","Guitare nylon","Guitare acier","Guitare jazz","Guitare clean",
        "Guitare etouffee","Guitare saturee","Guitare distorsion","Guitare harmoniques",
        "Basse acoustique","Basse finger","Basse pick","Basse fretless","Basse slap 1",
        "Basse slap 2","Basse synth 1","Basse synth 2","Violon","Alto","Violoncelle",
        "Contrebasse","Tremolo cordes","Pizzicato","Harpe","Timbales","Ensemble cordes 1",
        "Ensemble cordes 2","Cordes synth 1","Cordes synth 2","Choeur Aah","Choeur Ooh",
        "Voix synth","Coup d'orchestre","Trompette","Trombone","Tuba","Trompette sourdine",
        "Cor","Section cuivres","Cuivres synth 1","Cuivres synth 2","Saxophone soprano",
        "Saxophone alto","Saxophone tenor","Saxophone baryton","Hautbois","Cor anglais",
        "Basson","Clarinette","Piccolo","Flute","Flute a bec","Flute de Pan","Bouteille",
        "Shakuhachi","Sifflet","Ocarina","Lead carre","Lead dents de scie","Lead calliope",
        "Lead chiff","Lead charang","Lead voix","Lead quintes","Lead basse+lead",
        "Pad new age","Pad chaud","Pad polysynth","Pad choeur","Pad archet","Pad metallique",
        "Pad halo","Pad balayage","FX pluie","FX trame","FX cristal","FX atmosphere",
        "FX brillance","FX goblins","FX echos","FX sci-fi","Sitar","Banjo","Shamisen",
        "Koto","Kalimba","Cornemuse","Fiddle","Shanai","Tinkle bell","Agogo","Steel drums",
        "Woodblock","Taiko","Tom melodique","Synth drum","Cymbale inversee","Bruit guitare",
        "Bruit souffle","Bruit vagues","Bruit oiseaux","Bruit telephone","Bruit helicoptere",
        "Bruit applaudissements","Bruit coup de feu"
    ]
    mid = mido.MidiFile(path)
    tracks = []
    programs = {}
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'program_change':
                programs[msg.channel] = msg.program
    for track in mid.tracks:
        channels = {}
        for msg in track:
            if msg.type == 'note_on' and msg.velocity > 0:
                ch = msg.channel
                if ch not in channels:
                    channels[ch] = {"count": 0, "unique": set()}
                channels[ch]["count"] += 1
                channels[ch]["unique"].add(msg.note)
        for ch, info in channels.items():
            prog = programs.get(ch, 0)
            name = "Percussion" if ch == 9 else GM_INSTRUMENTS[prog] if prog < len(GM_INSTRUMENTS) else f"Programme {prog}"
            tracks.append({
                "channel": ch,
                "name": name,
                "program": prog,
                "notes": info["count"],
                "unique": len(info["unique"]),
            })
    seen = set()
    deduped = []
    for t in tracks:
        key = t["channel"]
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    return jsonify({"tracks": deduped, "filename": os.path.basename(path)})


@app.route("/api/midi-notes")
def midi_notes():
    from sounds import extract_notes_from_midi
    path = _get_midi_path()
    channels_param = request.args.get("channels", "")
    if path:
        if channels_param:
            channels = [int(c) for c in channels_param.split(",")]
        else:
            channels = None
        chords = extract_notes_from_midi(path, channel=None, filter_channels=channels)
        if chords:
            return jsonify(chords)
    return jsonify([[60], [62], [64], [65], [67], [69], [71], [72]])


@app.route("/api/export-start", methods=["POST", "OPTIONS"])
def export_start():
    """Launch export subprocess and return uid for polling."""
    if request.method == "OPTIONS":
        return "", 204
    import json, uuid, subprocess
    p = request.json
    uid = uuid.uuid4().hex[:8]
    params_file = os.path.join(PROJECT_DIR, f"_export_params_{uid}.json")
    output_file = os.path.join(PROJECT_DIR, f"_output_{uid}.mp4")
    with open(params_file, "w") as f:
        json.dump(p, f)
    subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_DIR, "_do_export.py"), params_file, output_file],
        cwd=PROJECT_DIR
    )
    return jsonify({"uid": uid})


@app.route("/api/export-poll/<uid>")
def export_poll(uid):
    output_file = os.path.join(PROJECT_DIR, f"_output_{uid}.mp4")
    if os.path.exists(output_file):
        return jsonify({"ready": True})
    return jsonify({"ready": False})


if __name__ == "__main__":
    print("Server: http://0.0.0.0:5000")
    app.run(host="0.0.0.0", debug=False, port=5000)
