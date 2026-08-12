# -*- coding: utf-8 -*-
"""统一元数据抽象层：把 ID3 / Vorbis Comment / MP4 / APEv2 / ASF 的差异
统一为一张字段字典，上层无需关心具体格式。"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional, Tuple
import mutagen
from mutagen.id3 import (APIC, COMM, ID3, TALB, TBPM, TCOM, TCON, TCOP, TEXT,
                         TIT2, TPE1, TPE2, TPOS, TPUB, TRCK, TSRC, TXXX,
                         TYER, TDRC, TENC, USLT)

TEXT_FIELDS = ["title", "album", "albumartist", "year", "genre", "isrc",
               "copyright", "publisher", "comment", "bpm", "encoder", "lyrics"]
LIST_FIELDS = ["artists", "composer", "arranger", "lyricist"]
NUM_FIELDS = ["track", "tracktotal", "disc", "disctotal"]
ALL_FIELDS = TEXT_FIELDS + LIST_FIELDS + NUM_FIELDS

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".ape", ".wav", ".aiff", ".aif", ".wv",
                        ".tta", ".m4a", ".mp4", ".ogg", ".mpc", ".opus", ".wma",
                        ".dsf", ".m4b", ".m4r"}
ID3_EXTENSIONS = {".mp3", ".wav", ".aiff", ".aif", ".dsf", ".tta"}
MP4_EXTENSIONS = {".m4a", ".mp4", ".m4b", ".m4r"}
APE_EXTENSIONS = {".ape", ".wv", ".mpc"}
VORBIS_EXTENSIONS = {".ogg", ".opus"}
ASF_EXTENSIONS = {".wma"}


class MetadataError(Exception):
    """元数据读写异常。"""


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS


def _split_multi(value, sep="/") -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        parts = []
        for v in value:
            parts.extend(str(v).split(sep))
    else:
        parts = str(value).split(sep)
    return [p.strip() for p in parts if p and p.strip()]


def _join_multi(values, sep="/") -> str:
    return sep.join(v.strip() for v in (values or []) if v and str(v).strip())


def _parse_num(value) -> Tuple[str, str]:
    if not value:
        return "", ""
    parts = str(value).split("/")
    cur = parts[0].strip()
    total = parts[1].strip() if len(parts) > 1 else ""
    return cur, total


def empty_fields() -> Dict[str, Any]:
    d: Dict[str, Any] = {f: "" for f in TEXT_FIELDS}
    for f in LIST_FIELDS:
        d[f] = []
    for f in NUM_FIELDS:
        d[f] = ""
    d["cover"] = b""
    d["cover_mime"] = ""
    d["duration"] = 0.0
    d["format"] = ""
    return d

class AudioFile:
    """封装一个音频文件，提供统一读写接口。"""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        if not os.path.isfile(self.path):
            raise MetadataError(f"文件不存在: {self.path}")
        ext = os.path.splitext(self.path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise MetadataError(f"不支持的音频格式: {ext}")
        self.ext = ext
        self.audio = self._load()
        self.last_error: Optional[str] = None

    #: 扩展名 -> mutagen 解析器（显式映射，避免内容嗅探误判）
    _PARSERS = None

    @classmethod
    def _parsers(cls):
        if cls._PARSERS is None:
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC
            from mutagen.apev2 import APEv2File as APE
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            from mutagen.wavpack import WavPack
            from mutagen.trueaudio import TrueAudio as TTA
            from mutagen.mp4 import MP4
            from mutagen.oggvorbis import OggVorbis
            from mutagen.musepack import Musepack
            from mutagen.oggopus import OggOpus
            from mutagen.asf import ASF
            from mutagen.dsf import DSF
            cls._PARSERS = {
                ".mp3": MP3, ".flac": FLAC, ".ape": APE, ".wav": WAVE,
                ".aiff": AIFF, ".aif": AIFF, ".wv": WavPack, ".tta": TTA,
                ".m4a": MP4, ".mp4": MP4, ".m4b": MP4, ".m4r": MP4,
                ".ogg": OggVorbis, ".mpc": Musepack, ".opus": OggOpus,
                ".wma": ASF, ".dsf": DSF,
            }
        return cls._PARSERS

    def _load(self):
        try:
            parser = self._parsers()[self.ext]
            return parser(self.path)
        except Exception as exc:
            raise MetadataError(f"读取文件失败: {exc}") from exc

    @property
    def duration(self) -> float:
        try:
            return float(self.audio.info.length)
        except Exception:
            return 0.0

    # ---------------- 读取 ----------------
    def read(self) -> Dict[str, Any]:
        fields = empty_fields()
        fields["duration"] = self.duration
        fields["format"] = self.ext.lstrip(".").upper()
        if self.ext in ID3_EXTENSIONS:
            self._read_id3(fields)
        elif self.ext in MP4_EXTENSIONS:
            self._read_mp4(fields)
        elif self.ext in APE_EXTENSIONS:
            self._read_ape(fields)
        elif self.ext in VORBIS_EXTENSIONS:
            self._read_vorbis(fields)
        elif self.ext in ASF_EXTENSIONS:
            self._read_asf(fields)
        elif self.ext == ".flac":
            self._read_flac(fields)
        return fields

    def _id3_tags(self) -> Optional[ID3]:
        tags = getattr(self.audio, "tags", None)
        return tags if isinstance(tags, ID3) else None

    def _read_id3(self, fields):
        tags = self._id3_tags()
        if tags is None:
            return

        def frame_text(frame_cls) -> str:
            for f in tags.getall(frame_cls.__name__):
                text = getattr(f, "text", None)
                if text:
                    return str(text[0]) if isinstance(text, (list, tuple)) else str(text)
            return ""

        fields["title"] = frame_text(TIT2)
        fields["album"] = frame_text(TALB)
        fields["artists"] = _split_multi(frame_text(TPE1))
        fields["albumartist"] = frame_text(TPE2)
        fields["composer"] = _split_multi(frame_text(TCOM))
        fields["arranger"] = _split_multi(self._get_txxx(tags, "ARRANGER"))
        fields["lyricist"] = _split_multi(frame_text(TEXT))
        fields["track"], fields["tracktotal"] = _parse_num(frame_text(TRCK))
        fields["disc"], fields["disctotal"] = _parse_num(frame_text(TPOS))
        fields["year"] = frame_text(TDRC) or frame_text(TYER)
        fields["genre"] = frame_text(TCON)
        fields["isrc"] = frame_text(TSRC)
        fields["copyright"] = frame_text(TCOP)
        fields["publisher"] = frame_text(TPUB)
        fields["bpm"] = frame_text(TBPM)
        fields["encoder"] = frame_text(TENC)
        for f in tags.getall("COMM"):
            if getattr(f, "desc", "") == "" and f.text:
                fields["comment"] = str(f.text[0])
                break
        for f in tags.getall("USLT"):
            if getattr(f, "desc", "") == "" and f.text:
                fields["lyrics"] = str(f.text)
                break
        for f in tags.getall("APIC"):
            if f.type == 3 or not fields["cover"]:
                fields["cover"] = f.data
                fields["cover_mime"] = str(f.mime)
                if f.type == 3:
                    break

    @staticmethod
    def _get_txxx(tags: ID3, key: str) -> str:
        for f in tags.getall("TXXX"):
            if str(f.desc).upper() == key.upper() and f.text:
                return str(f.text[0])
        return ""

    def _read_mp4(self, fields):
        tags = getattr(self.audio, "tags", None)
        if tags is None:
            return

        def text(*names):
            for n in names:
                if n in tags and tags[n]:
                    return str(tags[n][0])
            return ""

        def text_list(*names):
            for n in names:
                if n in tags and tags[n]:
                    out = []
                    for v in tags[n]:
                        out.extend(str(v).split("/"))
                    return [x.strip() for x in out if x.strip()]
            return []

        def custom(key):
            atom = f"----:com.apple.iTunes:{key}"
            return text(atom)

        fields["title"] = text("\xa9nam")
        fields["album"] = text("\xa9alb")
        fields["artists"] = text_list("\xa9ART")
        fields["albumartist"] = text("aART")
        fields["composer"] = text_list("\xa9wrt")
        fields["arranger"] = _split_multi(custom("ARRANGER"))
        fields["lyricist"] = _split_multi(custom("LYRICIST"))
        fields["year"] = text("\xa9day")
        fields["genre"] = text("\xa9gen")
        fields["lyrics"] = text("\xa9lyr")
        fields["isrc"] = custom("ISRC")
        fields["copyright"] = text("cprt")
        fields["comment"] = text("\xa9cmt")
        fields["encoder"] = text("\xa9too")
        if "trkn" in tags and tags["trkn"]:
            trk, tot = tags["trkn"][0]
            fields["track"] = str(trk) if trk else ""
            fields["tracktotal"] = str(tot) if tot else ""
        if "disk" in tags and tags["disk"]:
            dsk, tot = tags["disk"][0]
            fields["disc"] = str(dsk) if dsk else ""
            fields["disctotal"] = str(tot) if tot else ""
        if "tmpo" in tags and tags["tmpo"]:
            fields["bpm"] = str(tags["tmpo"][0])
        if "covr" in tags and tags["covr"]:
            data = tags["covr"][0]
            if isinstance(data, bytes):
                fields["cover"] = data
                fields["cover_mime"] = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png"

    def _read_ape(self, fields):
        tags = getattr(self.audio, "tags", None)
        if tags is None:
            return

        def get(key):
            if key in tags and tags[key]:
                v = tags[key][0]
                if isinstance(v, bytes):
                    try:
                        return v.decode("utf-8", "replace")
                    except Exception:
                        return ""
                return str(v)
            return ""

        mapping = {"title": "TITLE", "album": "ALBUM", "albumartist": "ALBUMARTIST",
                   "year": "YEAR", "genre": "GENRE", "lyrics": "LYRICS",
                   "isrc": "ISRC", "copyright": "COPYRIGHT", "publisher": "PUBLISHER",
                   "comment": "COMMENT", "bpm": "BPM", "encoder": "ENCODER"}
        for k, ape_key in mapping.items():
            fields[k] = get(ape_key)
        fields["artists"] = _split_multi(get("ARTIST"))
        fields["composer"] = _split_multi(get("COMPOSER"))
        fields["arranger"] = _split_multi(get("ARRANGER"))
        fields["lyricist"] = _split_multi(get("LYRICIST"))
        fields["track"], fields["tracktotal"] = _parse_num(get("TRACK") or get("TRACKNUMBER"))
        fields["disc"], fields["disctotal"] = _parse_num(get("DISC") or get("DISCNUMBER"))
        for key in ("COVER ART (FRONT)", "COVERART"):
            if key in tags and tags[key]:
                raw = tags[key][0]
                if isinstance(raw, bytes):
                    idx = raw.find(b"\x00")
                    data = raw[idx + 1:] if idx >= 0 else raw
                    fields["cover"] = data
                    fields["cover_mime"] = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png"
                    break

    def _read_vorbis_common(self, fields):
        tags = getattr(self.audio, "tags", None)
        if tags is None:
            return

        def get(key):
            if key in tags and tags[key]:
                return str(tags[key][0])
            return ""

        def get_list(key):
            if key in tags and tags[key]:
                return [str(v).strip() for v in tags[key] if str(v).strip()]
            return []

        mapping = {"title": "TITLE", "album": "ALBUM", "albumartist": "ALBUMARTIST",
                   "year": "DATE", "genre": "GENRE", "lyrics": "LYRICS",
                   "isrc": "ISRC", "copyright": "COPYRIGHT", "publisher": "PUBLISHER",
                   "comment": "COMMENT", "bpm": "BPM", "encoder": "ENCODER"}
        for k, vkey in mapping.items():
            fields[k] = get(vkey)
        fields["artists"] = get_list("ARTIST")
        fields["composer"] = get_list("COMPOSER")
        fields["arranger"] = get_list("ARRANGER")
        fields["lyricist"] = get_list("LYRICIST")
        fields["track"], fields["tracktotal"] = _parse_num(get("TRACKNUMBER") or get("TRACK"))
        fields["disc"], fields["disctotal"] = _parse_num(get("DISCNUMBER") or get("DISC"))

    def _read_vorbis(self, fields):
        self._read_vorbis_common(fields)
        tags = getattr(self.audio, "tags", None)
        if tags is not None and "METADATA_BLOCK_PICTURE" in tags:
            import base64
            from mutagen.flac import Picture
            try:
                pic = Picture(base64.b64decode(str(tags["METADATA_BLOCK_PICTURE"][0])))
                fields["cover"] = pic.data
                fields["cover_mime"] = pic.mime
            except Exception:
                pass

    def _read_flac(self, fields):
        self._read_vorbis_common(fields)
        pictures = getattr(self.audio, "pictures", None)
        if pictures:
            for pic in pictures:
                if pic.type == 3 or not fields["cover"]:
                    fields["cover"] = pic.data
                    fields["cover_mime"] = pic.mime
                    if pic.type == 3:
                        break

    def _read_asf(self, fields):
        tags = getattr(self.audio, "tags", None)
        if tags is None:
            return

        def get(*names):
            for n in names:
                if n in tags and tags[n]:
                    v = tags[n][0]
                    if isinstance(v, bytes):
                        try:
                            return v.decode("utf-8", "replace")
                        except Exception:
                            return ""
                    return str(v)
            return ""

        fields["title"] = get("Title")
        fields["album"] = get("WM/AlbumTitle", "Album")
        fields["artists"] = _split_multi(get("Author"))
        fields["albumartist"] = get("WM/AlbumArtist")
        fields["composer"] = _split_multi(get("WM/Composer"))
        fields["arranger"] = _split_multi(get("WM/Arranger"))
        fields["lyricist"] = _split_multi(get("WM/Writer"))
        fields["track"] = get("WM/TrackNumber")
        fields["disc"] = get("WM/PartOfSet")
        fields["year"] = get("WM/Year")
        fields["genre"] = get("WM/Genre")
        fields["lyrics"] = get("WM/Lyrics")
        fields["isrc"] = get("WM/ISRC")
        fields["copyright"] = get("Copyright")
        fields["publisher"] = get("WM/Publisher")
        fields["comment"] = get("Description")
        fields["bpm"] = get("WM/BeatsPerMinute")
        fields["encoder"] = get("WM/EncodingSettings")
        if "WM/Picture" in tags:
            try:
                from mutagen.asf import ASFPictureAttribute
                pic = tags["WM/Picture"][0]
                if isinstance(pic, ASFPictureAttribute) and pic.value:
                    fields["cover"] = pic.value
                    mime = pic.mime
                    fields["cover_mime"] = mime.decode("utf-8", "replace") if isinstance(mime, bytes) else str(mime)
            except Exception:
                pass

    # ---------------- 写入 ----------------
    def write(self, fields: Dict[str, Any]) -> None:
        try:
            if self.ext in ID3_EXTENSIONS:
                self._write_id3(fields)
            elif self.ext in MP4_EXTENSIONS:
                self._write_mp4(fields)
            elif self.ext in APE_EXTENSIONS:
                self._write_ape(fields)
            elif self.ext in VORBIS_EXTENSIONS:
                self._write_vorbis(fields, flac=False)
            elif self.ext in ASF_EXTENSIONS:
                self._write_asf(fields)
            elif self.ext == ".flac":
                self._write_vorbis(fields, flac=True)
            self._save()
        except MetadataError:
            raise
        except Exception as exc:
            raise MetadataError(f"写入标签失败: {exc}") from exc

    def _save(self):
        try:
            self.audio.save()
        except Exception as exc:
            raise MetadataError(f"保存文件失败: {exc}") from exc

    def _ensure_id3(self) -> ID3:
        tags = getattr(self.audio, "tags", None)
        if not isinstance(tags, ID3):
            # WAVE/AIFF/DSF/TTA 等格式的标签存放位置不同，必须用各自的
            # 专用 ID3 子类（add_tags 会创建正确的容器）
            add = getattr(self.audio, "add_tags", None)
            if add is not None:
                add()
            else:
                self.audio.tags = ID3()
            tags = self.audio.tags
        return tags

    @staticmethod
    def _set_frame(tags: ID3, frame_cls, value: str, desc: str = "") -> None:
        key = None
        for k in tags:
            f = tags[k]
            if isinstance(f, frame_cls) and getattr(f, "desc", "") == desc:
                key = k
                break
        if key:
            del tags[key]
        if value:
            if frame_cls is TXXX:
                tags.add(TXXX(encoding=3, desc=desc, text=[value]))
            else:
                tags.add(frame_cls(encoding=3, text=[value]))

    def _write_id3(self, fields):
        tags = self._ensure_id3()
        single = {"title": TIT2, "album": TALB, "albumartist": TPE2, "year": TDRC,
                  "genre": TCON, "isrc": TSRC, "copyright": TCOP, "publisher": TPUB,
                  "bpm": TBPM, "encoder": TENC}
        for name, frame_cls in single.items():
            self._set_frame(tags, frame_cls, str(fields.get(name) or ""))
        self._set_frame(tags, TPE1, _join_multi(fields.get("artists")))
        self._set_frame(tags, TCOM, _join_multi(fields.get("composer")))
        self._set_frame(tags, TXXX, _join_multi(fields.get("arranger")), desc="ARRANGER")
        self._set_frame(tags, TEXT, _join_multi(fields.get("lyricist")))
        self._set_frame(tags, TRCK, self._num_pair(fields, "track", "tracktotal"))
        self._set_frame(tags, TPOS, self._num_pair(fields, "disc", "disctotal"))

        for frame_id in ("COMM", "USLT"):
            if any(getattr(f, "desc", "") == "" for f in tags.getall(frame_id)):
                tags.delall(frame_id)
        if fields.get("comment"):
            tags.add(COMM(encoding=3, lang="eng", desc="", text=[str(fields["comment"])]))
        if fields.get("lyrics"):
            tags.add(USLT(encoding=3, lang="eng", desc="", text=str(fields["lyrics"])))

        if tags.getall("APIC"):
            tags.delall("APIC")
        if fields.get("cover"):
            mime = fields.get("cover_mime") or self._guess_mime(fields["cover"])
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="", data=bytes(fields["cover"])))

    @staticmethod
    def _num_pair(fields, cur, total) -> str:
        c = str(fields.get(cur) or "").strip()
        t = str(fields.get(total) or "").strip()
        return f"{c}/{t}" if c and t else c

    @staticmethod
    def _guess_mime(data: bytes) -> str:
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        return "image/jpeg"

    def _write_mp4(self, fields):
        from mutagen.mp4 import MP4Tags
        tags = getattr(self.audio, "tags", None)
        if not isinstance(tags, MP4Tags):
            tags = MP4Tags()
            self.audio.tags = tags

        def set_text(names, value, multi=False):
            if multi:
                vals = [x for x in (value or []) if x]
                for n in names:
                    tags[n] = vals
            else:
                v = [str(value)] if value else []
                for n in names:
                    tags[n] = v

        set_text(["\xa9nam"], fields.get("title"))
        set_text(["\xa9alb"], fields.get("album"))
        set_text(["\xa9ART"], fields.get("artists"), multi=True)
        set_text(["aART"], fields.get("albumartist"))
        set_text(["\xa9wrt"], fields.get("composer"), multi=True)
        set_text(["----:com.apple.iTunes:ARRANGER"], _join_multi(fields.get("arranger")))
        set_text(["----:com.apple.iTunes:LYRICIST"], _join_multi(fields.get("lyricist")))
        set_text(["\xa9day"], fields.get("year"))
        set_text(["\xa9gen"], fields.get("genre"))
        set_text(["\xa9lyr"], fields.get("lyrics"))
        set_text(["----:com.apple.iTunes:ISRC"], fields.get("isrc"))
        set_text(["cprt"], fields.get("copyright"))
        set_text(["\xa9cmt"], fields.get("comment"))
        set_text(["\xa9too"], fields.get("encoder"))

        def int_pair(cur, total):
            c = int(str(fields.get(cur) or "0").strip() or 0)
            t = int(str(fields.get(total) or "0").strip() or 0)
            return c, t

        tags["trkn"] = [int_pair("track", "tracktotal")]
        tags["disk"] = [int_pair("disc", "disctotal")]
        bpm = str(fields.get("bpm") or "").strip()
        tags["tmpo"] = [int(bpm)] if bpm.isdigit() else []
        if fields.get("cover"):
            tags["covr"] = [bytes(fields["cover"])]
        else:
            tags.pop("covr", None)

    def _write_ape(self, fields):
        from mutagen.apev2 import APEv2
        tags = getattr(self.audio, "tags", None)
        if not isinstance(tags, APEv2):
            tags = APEv2()
            self.audio.tags = tags
        mapping = {"title": "TITLE", "album": "ALBUM", "albumartist": "ALBUMARTIST",
                   "year": "YEAR", "genre": "GENRE", "lyrics": "LYRICS",
                   "isrc": "ISRC", "copyright": "COPYRIGHT", "publisher": "PUBLISHER",
                   "comment": "COMMENT", "bpm": "BPM", "encoder": "ENCODER"}
        for k, ape_key in mapping.items():
            v = str(fields.get(k) or "")
            if v:
                tags[ape_key] = v
            else:
                tags.pop(ape_key, None)
        for field, ape_key in (("artists", "ARTIST"), ("composer", "COMPOSER"),
                               ("arranger", "ARRANGER"), ("lyricist", "LYRICIST")):
            v = _join_multi(fields.get(field))
            if v:
                tags[ape_key] = v
            else:
                tags.pop(ape_key, None)
        for ape_key, cur, total in (("TRACK", "track", "tracktotal"), ("DISC", "disc", "disctotal")):
            v = self._num_pair(fields, cur, total)
            if v:
                tags[ape_key] = v
            else:
                tags.pop(ape_key, None)
        for key in ("COVER ART (FRONT)", "COVERART"):
            if key in tags:
                del tags[key]
        if fields.get("cover"):
            mime = fields.get("cover_mime") or self._guess_mime(fields["cover"])
            ext = ".jpg" if "jpeg" in mime else ".png"
            tags["COVER ART (FRONT)"] = f"cover{ext}".encode("utf-8") + b"\x00" + bytes(fields["cover"])

    def _write_vorbis(self, fields, flac: bool):
        tags = getattr(self.audio, "tags", None)
        if tags is None:
            if flac:
                from mutagen.flac import VCFLACDict
                tags = VCFLACDict()
                self.audio.tags = tags
            else:
                from mutagen.oggvorbis import VCommentDict
                tags = VCommentDict()
                self.audio.tags = tags
        mapping = {"title": "TITLE", "album": "ALBUM", "albumartist": "ALBUMARTIST",
                   "year": "DATE", "genre": "GENRE", "lyrics": "LYRICS",
                   "isrc": "ISRC", "copyright": "COPYRIGHT", "publisher": "PUBLISHER",
                   "comment": "COMMENT", "bpm": "BPM", "encoder": "ENCODER"}
        for k, vkey in mapping.items():
            v = str(fields.get(k) or "")
            if v:
                tags[vkey] = v
            else:
                tags.pop(vkey, None)
        multi = {"artists": "ARTIST", "composer": "COMPOSER",
                 "arranger": "ARRANGER", "lyricist": "LYRICIST"}
        for field, vkey in multi.items():
            vals = [x for x in (fields.get(field) or []) if x]
            if vals:
                tags[vkey] = vals
            else:
                tags.pop(vkey, None)
        for vkey, cur, total in (("TRACKNUMBER", "track", "tracktotal"),
                                 ("DISCNUMBER", "disc", "disctotal")):
            v = self._num_pair(fields, cur, total)
            if v:
                tags[vkey] = v
            else:
                tags.pop(vkey, None)

        if flac:
            from mutagen.flac import Picture
            pictures = getattr(self.audio, "pictures", None)
            if pictures:
                self.audio.clear_pictures()
            if fields.get("cover"):
                pic = Picture()
                pic.type = 3
                pic.mime = fields.get("cover_mime") or self._guess_mime(fields["cover"])
                pic.desc = ""
                pic.data = bytes(fields["cover"])
                self.audio.add_picture(pic)
        else:
            import base64
            from mutagen.flac import Picture
            tags.pop("METADATA_BLOCK_PICTURE", None)
            if fields.get("cover"):
                pic = Picture()
                pic.type = 3
                pic.mime = fields.get("cover_mime") or self._guess_mime(fields["cover"])
                pic.desc = ""
                pic.data = bytes(fields["cover"])
                tags["METADATA_BLOCK_PICTURE"] = base64.b64encode(pic.write()).decode("ascii")

    def _write_asf(self, fields):
        from mutagen.asf import ASFTags
        tags = getattr(self.audio, "tags", None)
        if not isinstance(tags, ASFTags):
            tags = ASFTags()
            self.audio.tags = tags
        mapping = {"title": "Title", "album": "WM/AlbumTitle",
                   "albumartist": "WM/AlbumArtist",
                   "year": "WM/Year", "genre": "WM/Genre",
                   "lyrics": "WM/Lyrics", "isrc": "WM/ISRC",
                   "copyright": "Copyright", "publisher": "WM/Publisher",
                   "comment": "Description", "bpm": "WM/BeatsPerMinute",
                   "encoder": "WM/EncodingSettings"}
        for k, asf_key in mapping.items():
            v = str(fields.get(k) or "")
            if v:
                tags[asf_key] = [v]
            else:
                tags.pop(asf_key, None)
        for field, asf_key in (("artists", "Author"), ("composer", "WM/Composer"),
                               ("arranger", "WM/Arranger"), ("lyricist", "WM/Writer")):
            v = _join_multi(fields.get(field))
            if v:
                tags[asf_key] = [v]
            else:
                tags.pop(asf_key, None)
        track = str(fields.get("track") or "").strip()
        total = str(fields.get("tracktotal") or "").strip()
        if track:
            tags["WM/TrackNumber"] = [f"{track}/{total}"] if total else [track]
        else:
            tags.pop("WM/TrackNumber", None)
        disc = str(fields.get("disc") or "").strip()
        if disc:
            tags["WM/PartOfSet"] = [disc]
        else:
            tags.pop("WM/PartOfSet", None)
        if fields.get("cover"):
            from mutagen.asf import ASFPictureAttribute
            pic = ASFPictureAttribute(
                mime=(fields.get("cover_mime") or self._guess_mime(fields["cover"])).encode("ascii"),
                value=bytes(fields["cover"]),
                picture_type=3)
            tags["WM/Picture"] = [pic]
        else:
            tags.pop("WM/Picture", None)

# ---------------------------------------------------------------------------
# ID3 版本互转（v1 <-> v2.3 <-> v2.4）
# ---------------------------------------------------------------------------

def convert_id3_version(path: str, version: str) -> Tuple[bool, str]:
    """转换 MP3/WAV/AIFF/DSF/TTA 的 ID3 标签版本。
    version 取值: "v1" / "v2.3" / "v2.4"。返回 (是否成功, 说明)。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in ID3_EXTENSIONS:
        return False, f"{ext} 不使用 ID3 标签，无需转换"
    parser = AudioFile._parsers()[ext]
    try:
        audio = parser(path)
    except Exception as exc:
        return False, f"读取失败: {exc}"
    try:
        if version == "v1":
            if ext != ".mp3":
                return False, "ID3v1 仅支持 MP3 文件"
            if not isinstance(getattr(audio, "tags", None), ID3):
                audio.add_tags()
            audio.save(v1=1, v2=0)
            return True, "已转换为 ID3v1"
        v2_ver = 4 if version == "v2.4" else 3
        if not isinstance(getattr(audio, "tags", None), ID3):
            audio.add_tags()
        if v2_ver == 4:
            audio.tags.update_to_v24()
        else:
            audio.tags.update_to_v23()
        audio.save(v2_version=v2_ver, v1=0)
        return True, f"已转换为 ID3v2.{v2_ver}"
    except Exception as exc:
        return False, f"转换失败: {exc}"


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def read_tags(path: str) -> Dict[str, Any]:
    """读取单个文件的统一字段。"""
    return AudioFile(path).read()


def write_tags(path: str, fields: Dict[str, Any]) -> None:
    """写入单个文件的统一字段。"""
    AudioFile(path).write(fields)


def find_audio_files(root: str, recursive: bool = True) -> List[str]:
    """递归查找目录下所有受支持的音频文件。"""
    files: List[str] = []
    if os.path.isfile(root):
        if is_supported(root):
            files.append(root)
        return files
    for dirpath, dirnames, filenames in os.walk(root):
        if not recursive:
            dirnames[:] = []
        for name in filenames:
            if is_supported(name):
                files.append(os.path.join(dirpath, name))
    return files
