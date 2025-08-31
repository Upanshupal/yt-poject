# app.py
from flask import Flask, request, jsonify, send_file, render_template, after_this_request
from flask_cors import CORS
import yt_dlp
import os
import re
import uuid
import subprocess

app = Flask(__name__, template_folder="templates")
CORS(app)

# Temporary download folder
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Regex for YouTube URLs
YOUTUBE_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
    r'(watch\?v=|embed/|v/|shorts/|.+\?v=)?([^&=%\?]{11})'
)

def is_valid_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_REGEX.match(url or ""))

def check_ffmpeg():
    """Check if ffmpeg is installed and available in PATH"""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception:
        return False

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/videoinfo", methods=["GET"])
def video_info():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get("formats", []):
            fmt = {
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "height": f.get("height"),
                "width": f.get("width"),
                "fps": f.get("fps"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "format_note": f.get("format_note"),
                "abr": f.get("abr"),
                "tbr": f.get("tbr"),
                "asr": f.get("asr"),
                "protocol": f.get("protocol"),
                "container": f.get("container"),
                "progressive": (f.get("vcodec") != "none" and f.get("acodec") != "none"),
                "audio_only": (f.get("vcodec") == "none" and f.get("acodec") != "none"),
                "video_only": (f.get("vcodec") != "none" and f.get("acodec") == "none"),
                "quality_label": f.get("format") or f.get("format_note") or f.get("quality"),
            }
            if fmt["ext"] in ("mp4", "webm", "m4a", "mp3", "opus"):
                formats.append(fmt)

        # Sorting: progressive → video-only → audio-only
        def sort_key(f):
            group = 0 if f["progressive"] else (1 if f["video_only"] else 2)
            height = f["height"] or 0
            abr = f["abr"] or 0
            return (group, -height, -abr)

        formats.sort(key=sort_key)

        return jsonify({
            "id": info.get("id"),
            "title": info.get("title"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "thumbnail": info.get("thumbnail") or (info.get("thumbnails") or [{}])[-1].get("url"),
            "formats": formats,
            "original_url": url,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to fetch video info: {e}"}), 500

@app.route("/api/download", methods=["GET"])
def download():
    url = request.args.get("url", "").strip()
    format_id = request.args.get("format_id", "").strip()  # ✅ selected quality from frontend

    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400

    # ✅ If no format_id provided, fallback to best
    format_spec = format_id if format_id else "bestvideo+bestaudio/best"

    if not check_ffmpeg():
        return jsonify({"error": "⚠️ ffmpeg is not installed or not in PATH. Please install ffmpeg."}), 500

    uid = uuid.uuid4().hex
    outtmpl = os.path.join(DOWNLOAD_FOLDER, uid + ".%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": format_spec,   # ✅ respect selected quality
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "geo_bypass": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            final_path = ydl.prepare_filename(info)

            if not os.path.exists(final_path):
                alt = os.path.splitext(final_path)[0] + ".mp4"
                if os.path.exists(alt):
                    final_path = alt

        if not os.path.exists(final_path):
            return jsonify({"error": "File not found after download"}), 500

        title = (info.get("title") or "video").strip()
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
        ext = os.path.splitext(final_path)[1].lstrip(".") or "mp4"

        # ✅ Delete file after sending response
        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
            except Exception as e:
                print(f"Cleanup error: {e}")
            return response

        return send_file(final_path, as_attachment=True, download_name=f"{safe_title}.{ext}")

    except Exception as e:
        return jsonify({"error": f"Download failed: {e}"}), 500

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
