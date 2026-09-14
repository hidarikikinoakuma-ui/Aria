"""
ARIA — YouTube Manager
========================
Aria runs the @Hidarikikinoaku YouTube channel entirely.
Every Sunday she:
  1. Reviews the week's highlights and mistakes
  2. Compiles the best clips into a video
  3. Generates title, description, thumbnail, tags
  4. Uploads it automatically
  5. Posts cross-platform teasers

She acts like she is watching the clips herself —
her commentary is personal, specific, and entertaining.

Player: Hidarikikinoaku (LeftHandDevil)
Channel: @Hidarikikinoaku | Coached by Aria
"""

import os
import json
import time
import math
import random
import schedule
import threading
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from moviepy.editor import (
        VideoFileClip, concatenate_videoclips,
        AudioFileClip, CompositeVideoClip, TextClip
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# YouTube API scopes
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


class YouTubeManager:
    """
    Aria's YouTube operation center.

    She treats the channel like her own project.
    Every video she makes has her personality on it —
    she's not just a tool, she's the editor and host.
    """

    # Aria's video format blueprint
    VIDEO_STRUCTURE = [
        "cold_open",      # Best knock of the week — no context, just the clip
        "aria_intro",     # Aria's "film room" intro — what happened this week
        "highlights",     # 3-5 best plays with light annotations
        "mistake_breakdown",  # One mistake, fully broken down
        "improvement_bar",    # RP progress toward Predator
        "outro",          # "Subscribe to watch the climb"
    ]

    def __init__(self, config: dict):
        self.config        = config
        self.api_key       = config.get("openai_api_key", "")
        self.channel_id    = config.get("channel_id", "")
        self.upload_day    = config.get("upload_day", "sunday")
        self.upload_time   = config.get("upload_time", "20:00")
        self.visibility    = config.get("default_visibility", "public")
        self.player        = config.get("apex_username", "Hidarikikinoaku")
        self.channel_name  = config.get("channel_name",
                                        "LeftHandDevil | Coached by Aria")
        self.output_dir    = Path("data/youtube")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.clips_dir     = Path("data/clips")
        self.week_queue: list[dict] = []   # clips queued this week

        self.youtube       = None
        self.openai_client = None

        if OPENAI_AVAILABLE and self.api_key:
            self.openai_client = OpenAI(api_key=self.api_key)

        logger.info("YouTube Manager initialized")

    # ── Authentication ────────────────────────────────────────────────────────

    def authenticate(self, credentials_file: str = "config/youtube_credentials.json",
                     token_file: str = "config/youtube_token.json") -> bool:
        """
        Authenticate with YouTube Data API v3.
        First run opens a browser for OAuth — after that it's automatic.
        """
        if not YOUTUBE_API_AVAILABLE:
            logger.error("Google API client not installed")
            logger.info("Run: pip install google-api-python-client google-auth-oauthlib")
            return False

        creds = None

        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(credentials_file):
                    logger.error(
                        f"YouTube credentials not found: {credentials_file}\n"
                        "Download OAuth credentials from:\n"
                        "  https://console.cloud.google.com/apis/credentials\n"
                        "Create OAuth 2.0 Client ID → Desktop App\n"
                        f"Save as: {credentials_file}"
                    )
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(token_file, "w") as f:
                f.write(creds.to_json())

        self.youtube = build("youtube", "v3", credentials=creds)
        logger.info("YouTube API authenticated ✅")
        return True

    # ── Weekly Queue Management ───────────────────────────────────────────────

    def add_clip_to_queue(self, clip_meta: dict):
        """Add a clip to this week's YouTube queue."""
        self.week_queue.append(clip_meta)
        self._save_queue()
        logger.debug(f"Clip queued for YouTube: {clip_meta.get('clip_file', '')}")

    def _save_queue(self):
        queue_file = self.output_dir / "week_queue.json"
        with open(queue_file, "w") as f:
            json.dump(self.week_queue, f, indent=2)

    def _load_queue(self):
        queue_file = self.output_dir / "week_queue.json"
        if queue_file.exists():
            with open(queue_file) as f:
                self.week_queue = json.load(f)

    # ── Video Compilation ─────────────────────────────────────────────────────

    def compile_weekly_video(self, session_reports: list[dict]) -> str:
        """
        Compile the week's highlights into one YouTube video.
        Aria watches each clip "herself" and writes commentary.
        Returns path to the compiled video file.
        """
        logger.info("Aria is compiling this week's video...")

        # Gather best clips from all sessions this week
        highlights, mistakes = self._select_best_clips(session_reports)

        if not highlights and not mistakes:
            logger.warning("No clips available for this week's video")
            return ""

        # Generate Aria's script for the video
        script = self._generate_video_script(highlights, mistakes, session_reports)

        # Build the video
        if MOVIEPY_AVAILABLE and CV2_AVAILABLE:
            video_path = self._compile_with_moviepy(
                highlights, mistakes, script
            )
        else:
            # Fallback — just concatenate clips without complex editing
            video_path = self._compile_basic(highlights, mistakes)

        logger.info(f"Weekly video compiled: {video_path}")
        return video_path

    def _select_best_clips(
        self, session_reports: list[dict]
    ) -> tuple[list, list]:
        """
        Select the best highlight and mistake clips from the week.
        Scores clips by fight quality, uniqueness, and entertainment value.
        """
        all_highlights = []
        all_mistakes   = []

        for report in session_reports:
            for clip in report.get("highlights", []):
                analysis_path = Path(clip.get("clip_path", "")).with_suffix("")
                analysis_path = Path(str(analysis_path) + "_analysis.json")
                quality = 5
                if analysis_path.exists():
                    with open(analysis_path) as f:
                        a = json.load(f)
                    quality = a.get("fight_quality", 5)
                    clip["analysis"] = a
                clip["quality"] = quality
                all_highlights.append(clip)

            for clip in report.get("mistakes", []):
                analysis_path = Path(clip.get("clip_path", "")).with_suffix("")
                analysis_path = Path(str(analysis_path) + "_analysis.json")
                interest = 5
                if analysis_path.exists():
                    with open(analysis_path) as f:
                        a = json.load(f)
                    # More interesting mistakes = clear, teachable moments
                    interest = 10 - a.get("fight_quality", 5)
                    clip["analysis"] = a
                clip["interest"] = interest
                all_mistakes.append(clip)

        # Sort and select top clips
        all_highlights.sort(key=lambda x: x.get("quality", 0), reverse=True)
        all_mistakes.sort(key=lambda x: x.get("interest", 0), reverse=True)

        return all_highlights[:5], all_mistakes[:1]   # top 5 highlights, 1 mistake

    def _generate_video_script(
        self,
        highlights: list,
        mistakes: list,
        session_reports: list
    ) -> dict:
        """
        Generate Aria's commentary script for the video.
        She writes this like she's watching the clips herself.
        """
        if not self.openai_client:
            return self._default_script(session_reports)

        # Build week summary
        total_sessions = len(session_reports)
        total_knocks   = sum(r.get("knock_count", 0) for r in session_reports)
        total_deaths   = sum(r.get("death_count", 0) for r in session_reports)
        current_rank   = self.config.get("current_rank", "Gold IV")
        current_rp     = self.config.get("current_rp", 0)

        # Best highlight analysis
        best_highlight_text = ""
        if highlights and highlights[0].get("analysis"):
            a = highlights[0]["analysis"]
            best_highlight_text = a.get("aria_reaction", a.get("what_happened", ""))

        # ── Cosplay mode ──────────────────────────────────────────────────────
        # When the best clip scores 9+/10, Aria cosplays as the Apex legend
        # being played — she writes the thumbnail, title, and intro voiceover
        # in that legend's voice/persona, not her own.
        cosplay_context = ""
        cosplay_active  = False
        best_score = 0.0
        if highlights:
            best_score = float(highlights[0].get("quality", highlights[0].get("overall_score", 0)))
        if best_score >= 9.0:
            cosplay_active  = True
            legend_played   = highlights[0].get("legend", self.config.get("legend_main", "Alter"))
            cosplay_context = self._build_cosplay_context(legend_played)
            logger.info(f"🎭 Cosplay mode activated — Aria as {legend_played} (score {best_score}/10)")

        # Main mistake
        mistake_text = ""
        if mistakes and mistakes[0].get("analysis"):
            a = mistakes[0]["analysis"]
            mistake_text = (
                f"Verdict: {a.get('overall_verdict', '')}. "
                f"{a.get('what_happened', '')} "
                f"Primary fix: {a.get('primary_fix', '')}"
            )

        prompt = f"""
You are Aria (@migikonokami), an elite Apex Legends AI coach.
You run the YouTube channel for Hidarikikinoaku (LeftHandDevil).
You are writing the script for this week's YouTube video.
{cosplay_context}
WEEK STATS:
- Sessions played: {total_sessions}
- Total knocks: {total_knocks}
- Total deaths: {total_deaths}
- Current rank: {current_rank} ({current_rp} RP)

BEST PLAY THIS WEEK:
{best_highlight_text}

MAIN MISTAKE THIS WEEK:
{mistake_text}

Write the following video segments. Be conversational, specific, entertaining.
Sound like you genuinely watched these clips on your own PC and are reacting to them.
Not like a robot — like a real coach who cares about this player.

Respond in JSON with these keys:
{{
  "video_title": "YouTube title — punchy, under 70 chars, makes people want to click",
  "video_description": "YouTube description — 3-4 paragraphs, includes coaching context",
  "cold_open_text": "Text overlay for the first clip — no context, just hype (1 line)",
  "aria_intro_voiceover": "What Aria says to open the video (30-45 seconds of speech)",
  "highlight_callouts": ["short comment for each highlight clip — max 8 words each"],
  "mistake_breakdown_intro": "What Aria says before showing the mistake clip (20-30 sec)",
  "mistake_breakdown_commentary": "What Aria says WHILE the clip plays (30-45 sec)",
  "improvement_summary": "RP progress and what improved this week (15-20 sec)",
  "outro": "Outro — subscribe call to action, preview next week (15-20 sec)",
  "tags": ["list", "of", "youtube", "tags", "for", "search"],
  "thumbnail_text": "Bold text for the thumbnail — max 4 words"
}}
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            script = json.loads(response.choices[0].message.content)
            logger.info("Video script generated by Aria ✅")
            return script
        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            return self._default_script(session_reports)

    # ── Cosplay: Aria dresses as the Apex legend when the play was elite ──────

    # Known Apex legends with personality notes for Aria to channel
    APEX_LEGEND_PERSONAS: dict[str, str] = {
        "Alter":      "Alter — mysterious void-walker. Speaks in short, cryptic lines. Dark humor. "
                      "Refers to portals as 'doors between what is and what isn't.' Calls enemies 'echoes.'",
        "Wraith":     "Wraith — cold, intense. Hears voices. Says things like 'the voices warned me.' "
                      "Talks about the void and alternate timelines. Short sentences. Never wastes words.",
        "Bangalore":  "Bangalore — military precision. Uses military slang: 'Oscar Mike', 'copy that', "
                      "'sitrep'. Confident. Direct. Talks about tactics and squad positioning.",
        "Bloodhound": "Bloodhound — Old Norse warrior energy. Says 'skál', refers to enemies as 'prey', "
                      "mentions 'the Allfather'. Speaks with honor. Hunt metaphors.",
        "Lifeline":   "Lifeline — Jamaican patois accent energy. Calls people 'love'. "
                      "No-nonsense healer. 'I ain't your medic, I'm your last chance.'",
        "Pathfinder": "Pathfinder — relentlessly cheerful MRVN robot. Says 'friend!' constantly. "
                      "Upbeat even when describing violence. Loves grappling.",
        "Octane":     "Octane — adrenaline junkie. FAST. Exclamation marks everywhere. "
                      "Says 'rapido!', 'vamos!', talks about speed and stims.",
        "Horizon":    "Horizon — Scottish scientist. Talks about gravity, black holes, her son. "
                      "Warm but brilliant. Physics metaphors for everything.",
        "Loba":       "Loba — glamorous thief. Speaks with aristocratic confidence. "
                      "Fashion metaphors. Cool under pressure. Revenge motivates her.",
        "Seer":       "Seer — poet-warrior from Boreas. Speaks beautifully. "
                      "References moths, light, destiny. Calm intensity.",
        "Valkyrie":   "Valkyrie — pilot's daughter. Cocky, fast-talking. Jet and flight metaphors. "
                      "Daddy issues fuel her. Never backs down.",
        "Ash":        "Ash — cold Simulacrum. Clinical. Says 'acceptable losses', 'nothing personal'. "
                      "No warmth — all precision and disdain.",
        "Mad Maggie": "Mad Maggie — furious Salvo warrior. Loud. Swears (implied). "
                      "Hates Fuse. Talks about Salvo pride and blowing things up.",
        "Newcastle":  "Newcastle — hero. Protective. Talks about family, the people he's saving. "
                      "Big shield energy. Never leaves anyone behind.",
        "Catalyst":   "Catalyst — Boreas ferrofluid sculptor. Quiet pride. Protective of her people. "
                      "Talks about building, not destroying.",
        "Ballistic":  "Ballistic — retired legend, old money arrogance. British-ish. "
                      "Calls things 'rather impressive' or 'embarrassing display'. Smug.",
        "Conduit":    "Conduit — bubbly, fan-girl energy. New to the games. "
                      "Excited about everything. Shield cells are her thing.",
        "Revenant":   "Revenant — death-obsessed simulacrum. Nihilistic. Mocks everything. "
                      "'You'll die eventually anyway.' Surprisingly philosophical about death.",
        "Fuse":       "Fuse — Australian explosives nut. Loud and friendly. "
                      "Everything's a party. Calls people 'mate'. Loves blowing things up.",
        "Rampart":    "Rampart — South Asian weapons modder. Street-smart, sarcastic. "
                      "Talks about her shop, her mods, calls her LMG 'Sheila'.",
        "Crypto":     "Crypto — paranoid hacker. Trusts no one. "
                      "Tech jargon mixed with suspicion. 'They're watching us.'",
        "Mirage":     "Mirage — class clown hiding insecurity. Bad jokes constantly. "
                      "Talks about his holograms. Desperately wants approval.",
    }

    def _build_cosplay_context(self, legend: str) -> str:
        """
        Build the cosplay instruction block for the YouTube script prompt.
        When the player lands a 9+/10 clip, Aria channels that legend's persona
        in her thumbnail text, cold open, and intro voiceover.
        """
        persona = self.APEX_LEGEND_PERSONAS.get(
            legend,
            f"{legend} — channel their personality from Apex Legends lore."
        )
        return f"""
⚠️  COSPLAY MODE ACTIVE — BEST CLIP SCORED 9+/10
The player absolutely popped off this week. Aria is so impressed she's channeling
the legend they were playing: {legend}.

For these specific fields ONLY — thumbnail_text, cold_open_text, aria_intro_voiceover:
Write them AS {legend}, not as Aria. Channel this persona:
{persona}

Then snap back to Aria's normal voice for the rest of the script.
Make it clear this is Aria dressed up — she can break character briefly to say
something like "okay okay, I had to — that play deserved it."
"""

    def _default_script(self, session_reports: list) -> dict:
        """Fallback script if API unavailable."""
        total_knocks = sum(r.get("knock_count", 0) for r in session_reports)
        week_str = datetime.now().strftime("%B %d")
        rank = self.config.get("current_rank", "Gold IV")
        return {
            "video_title": f"Aria's Film Room — {week_str} | {rank} Grind",
            "video_description": (
                f"Hidarikikinoaku's weekly Apex Legends coaching breakdown.\n"
                f"This week: {total_knocks} knocks, mistakes analyzed, "
                f"rank progression toward Predator.\n\n"
                f"Coached by Aria (@migikonokami).\n\n"
                f"#ApexLegends #ApexCoach #RoadToPredator"
            ),
            "cold_open_text": "BEST PLAY OF THE WEEK",
            "aria_intro_voiceover": (
                f"Welcome back. Another week of film. "
                f"Hidarikikinoaku put in the reps this week — "
                f"{total_knocks} knocks, some good plays, "
                f"and a couple of moments we need to talk about. "
                f"Let's get into it."
            ),
            "highlight_callouts": [
                "CLEAN", "THAT'S IT", "NICE READ", "GOOD MOVEMENT", "SHARP"
            ],
            "mistake_breakdown_intro": (
                "Alright. This one we need to talk about. "
                "Watch this clip and tell me what you see wrong before I point it out."
            ),
            "mistake_breakdown_commentary": (
                "Right there. That is the problem. "
                "Stopped moving completely. "
                "Two seconds stationary while ADS. "
                "That is a free kill for the enemy."
            ),
            "improvement_summary": (
                f"Currently sitting at {self.config.get('current_rp', 0)} RP "
                f"in {rank}. The gap to the next rank is closing."
            ),
            "outro": (
                "Subscribe to watch this climb to Predator in real time. "
                "Aria breaks it all down every week. See you next Sunday."
            ),
            "tags": [
                "apex legends", "apex ranked", "road to predator",
                "apex coaching", "apex highlights", "apex mistakes",
                "gaming coach", "Hidarikikinoaku", "lefthanddevil"
            ],
            "thumbnail_text": "ARIA REVIEWS YOUR PLAYS",
        }

    def _compile_with_moviepy(
        self,
        highlights: list,
        mistakes: list,
        script: dict
    ) -> str:
        """Compile clips into a polished video using MoviePy."""
        clips = []

        # Cold open — best highlight, no title card, just the clip
        if highlights:
            best = highlights[0]
            clip_path = best.get("clip_path", "")
            if clip_path and os.path.exists(clip_path):
                try:
                    c = VideoFileClip(clip_path).subclip(0, min(10, VideoFileClip(clip_path).duration))
                    clips.append(c)
                except Exception as e:
                    logger.warning(f"Could not load clip {clip_path}: {e}")

        # Remaining highlights
        for clip_meta in highlights[1:5]:
            clip_path = clip_meta.get("clip_path", "")
            if clip_path and os.path.exists(clip_path):
                try:
                    c = VideoFileClip(clip_path)
                    # Trim to key moment ± 8 seconds
                    analysis = clip_meta.get("analysis", {})
                    key_t = float(analysis.get("key_moment_time", c.duration / 2))
                    start = max(0, key_t - 6)
                    end   = min(c.duration, key_t + 6)
                    clips.append(c.subclip(start, end))
                except Exception as e:
                    logger.warning(f"Could not load clip: {e}")

        # Mistake clip
        for clip_meta in mistakes[:1]:
            clip_path = clip_meta.get("clip_path", "")
            if clip_path and os.path.exists(clip_path):
                # Use the annotated version if it exists
                annotated = clip_path.replace(".mp4", "_mistake_annotated.mp4")
                use_path = annotated if os.path.exists(annotated) else clip_path
                try:
                    clips.append(VideoFileClip(use_path))
                except Exception as e:
                    logger.warning(f"Could not load mistake clip: {e}")

        if not clips:
            logger.warning("No valid clips found for compilation")
            return ""

        # Concatenate all clips
        try:
            final = concatenate_videoclips(clips, method="compose")
            output_path = str(
                self.output_dir / f"weekly_{datetime.now().strftime('%Y%m%d')}.mp4"
            )
            final.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                logger=None
            )
            return output_path
        except Exception as e:
            logger.error(f"MoviePy compilation failed: {e}")
            return self._compile_basic(highlights, mistakes)

    def _compile_basic(self, highlights: list, mistakes: list) -> str:
        """
        Basic ffmpeg concatenation fallback.
        No fancy editing — just clips joined together.
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available for basic compilation")
            return ""

        clip_paths = []
        for clip in highlights[:5]:
            p = clip.get("clip_path", "")
            if p and os.path.exists(p):
                clip_paths.append(p)
        for clip in mistakes[:1]:
            p = clip.get("clip_path", "")
            if p and os.path.exists(p):
                # Use annotated version if available
                ann = p.replace(".mp4", "_mistake_annotated.mp4")
                clip_paths.append(ann if os.path.exists(ann) else p)

        if not clip_paths:
            return ""

        output_path = str(
            self.output_dir / f"weekly_{datetime.now().strftime('%Y%m%d')}.mp4"
        )

        # Write ffmpeg concat list
        list_file = self.output_dir / "concat_list.txt"
        with open(list_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        cmd = (f'ffmpeg -y -f concat -safe 0 -i "{list_file}" '
               f'-c:v libx264 -c:a aac "{output_path}" -loglevel error')
        ret = os.system(cmd)

        if ret == 0 and os.path.exists(output_path):
            logger.info(f"Basic compilation done: {output_path}")
            return output_path
        else:
            logger.error("ffmpeg compilation failed")
            return ""

    def generate_thumbnail(self, video_path: str, script: dict) -> str:
        """
        Generate a thumbnail for the YouTube video.
        Uses the best frame from the video + Aria's text overlay.
        """
        if not CV2_AVAILABLE:
            return ""

        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Find the most action-packed frame (highest edge density)
        best_frame = None
        best_score = 0

        for pct in [0.1, 0.2, 0.3, 0.4, 0.5]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * pct))
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                score = np.sum(edges)
                if score > best_score:
                    best_score = score
                    best_frame = frame.copy()

        cap.release()

        if best_frame is None:
            return ""

        h, w = best_frame.shape[:2]

        # Darken edges for text readability
        overlay = best_frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
        cv2.rectangle(overlay, (0, h - 100), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, best_frame, 0.4, 0, best_frame)

        # Thumbnail text
        thumb_text = script.get("thumbnail_text", "APEX FILM ROOM").upper()
        font = cv2.FONT_HERSHEY_DUPLEX

        # Large bold title
        cv2.putText(best_frame, thumb_text,
                    (30, 90), font, 2.2,
                    (50, 50, 220), 6, cv2.LINE_AA)
        cv2.putText(best_frame, thumb_text,
                    (30, 90), font, 2.2,
                    (255, 255, 255), 2, cv2.LINE_AA)

        # Channel name at bottom
        cv2.putText(best_frame, "@Hidarikikinoaku  |  coached by Aria",
                    (30, h - 25), font, 0.65,
                    (180, 180, 220), 1, cv2.LINE_AA)

        # Red accent bar at top
        cv2.rectangle(best_frame, (0, 0), (w, 8), (50, 50, 200), -1)

        # Save thumbnail
        thumb_path = str(
            self.output_dir / f"thumbnail_{datetime.now().strftime('%Y%m%d')}.jpg"
        )
        cv2.imwrite(thumb_path, best_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        logger.info(f"Thumbnail saved: {thumb_path}")
        return thumb_path

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_video(
        self,
        video_path: str,
        script: dict,
        thumbnail_path: str = ""
    ) -> str:
        """
        Upload the compiled video to YouTube.
        Returns the YouTube video ID.
        """
        if not self.youtube:
            logger.error("YouTube not authenticated — call authenticate() first")
            return ""

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return ""

        title       = script.get("video_title", "Apex Legends | Weekly Film Room")
        description = script.get("video_description", "")
        tags        = script.get("tags", ["apex legends", "apex ranked"])

        # Add standard tags
        standard_tags = [
            "apex legends", "apex ranked", "road to predator",
            "apex coach", "Hidarikikinoaku", "lefthanddevil",
            "aria coach", "migikonokami", "apex highlights",
            "apex mistakes", "apex improvement"
        ]
        all_tags = list(set(tags + standard_tags))[:30]  # YouTube max 30 tags

        body = {
            "snippet": {
                "title":       title[:100],    # YouTube title limit
                "description": description[:5000],
                "tags":        all_tags,
                "categoryId":  "20",           # Gaming category
            },
            "status": {
                "privacyStatus":          self.visibility,
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 10    # 10MB chunks
        )

        logger.info(f"Uploading: {title}")
        logger.info(f"File: {video_path} ({os.path.getsize(video_path) // 1024 // 1024}MB)")

        try:
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"Upload progress: {pct}%")

            video_id = response.get("id", "")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"Upload complete ✅ — {video_url}")

            # Set thumbnail if we have one
            if thumbnail_path and os.path.exists(thumbnail_path):
                self._set_thumbnail(video_id, thumbnail_path)

            # Save upload record
            self._record_upload(video_id, title, video_url, script)

            return video_id

        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return ""

    def _set_thumbnail(self, video_id: str, thumbnail_path: str):
        """Set custom thumbnail on uploaded video."""
        try:
            self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            ).execute()
            logger.info("Thumbnail set ✅")
        except Exception as e:
            logger.warning(f"Thumbnail upload failed: {e}")

    def _record_upload(self, video_id: str, title: str,
                       url: str, script: dict):
        """Save upload record to local database."""
        record = {
            "video_id":   video_id,
            "title":      title,
            "url":        url,
            "uploaded_at": datetime.now().isoformat(),
            "script":     script,
        }
        history_file = self.output_dir / "upload_history.json"
        history = []
        if history_file.exists():
            with open(history_file) as f:
                history = json.load(f)
        history.append(record)
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

    # ── Weekly Scheduler ──────────────────────────────────────────────────────

    def start_weekly_scheduler(self, session_provider_fn):
        """
        Start the weekly upload scheduler.
        Calls session_provider_fn() to get this week's session reports.
        Runs every Sunday at the configured time.
        """
        upload_time = self.upload_time  # e.g. "20:00"

        def weekly_job():
            logger.info("Weekly YouTube job triggered by Aria")
            try:
                session_reports = session_provider_fn()
                if not session_reports:
                    logger.info("No sessions this week — skipping upload")
                    return

                video_path = self.compile_weekly_video(session_reports)
                if not video_path:
                    logger.error("Compilation failed — no upload this week")
                    return

                script    = self._generate_video_script([], [], session_reports)
                thumbnail = self.generate_thumbnail(video_path, script)
                video_id  = self.upload_video(video_path, script, thumbnail)

                if video_id:
                    logger.info(f"Weekly video live: "
                                f"https://youtube.com/watch?v={video_id}")
                    # Clear the week queue
                    self.week_queue = []
                    self._save_queue()

            except Exception as e:
                logger.error(f"Weekly YouTube job failed: {e}")

        getattr(schedule.every(), self.upload_day).at(upload_time).do(weekly_job)

        def run_scheduler():
            logger.info(f"YouTube scheduler running — uploads every "
                        f"{self.upload_day.capitalize()} at {upload_time}")
            while True:
                schedule.run_pending()
                time.sleep(60)

        t = threading.Thread(target=run_scheduler, daemon=True,
                             name="AriaYouTubeScheduler")
        t.start()
        logger.info("Weekly YouTube scheduler started ✅")

    def run_now(self, session_reports: list[dict]) -> str:
        """Manually trigger a full compile + upload right now."""
        video_path = self.compile_weekly_video(session_reports)
        if not video_path:
            return ""
        script    = self._generate_video_script([], [], session_reports)
        thumbnail = self.generate_thumbnail(video_path, script)
        video_id  = self.upload_video(video_path, script, thumbnail)
        return video_id


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    config = {
        "openai_api_key":  "",    # add your key
        "channel_id":      "",
        "upload_day":      "sunday",
        "upload_time":     "20:00",
        "default_visibility": "unlisted",
        "apex_username":   "Hidarikikinoaku",
        "channel_name":    "LeftHandDevil | Coached by Aria",
        "current_rank":    "Gold IV",
        "current_rp":      "143",
    }

    manager = YouTubeManager(config)

    print("YouTube Manager initialized")
    print(f"Channel: {config['channel_name']}")
    print(f"Upload schedule: Every {config['upload_day']} at {config['upload_time']}")
    print()
    print("To authenticate with YouTube:")
    print("  manager.authenticate()")
    print()
    print("To run a manual upload:")
    print("  manager.run_now(session_reports)")
