import asyncio
import random
import re
from typing import List, Tuple
from datetime import datetime

class HumanizerService:
    """Makes Luna's responses feel human - typos, delays, message splitting"""
    
    TYPO_REPLACEMENTS = {
        'a': ['s', 'q'], 'e': ['r', 'w'], 'i': ['u', 'o'],
        'o': ['i', 'p'], 't': ['r', 'y'], 's': ['a', 'd'],
        'u': ['i', 'y'], 'n': ['b', 'm'], 'm': ['n', 'k']
    }
    
    MOOD_EMOJIS = {
        "happy": ["😊", "🥰", "😄", "✨", "💕"],
        "playful": ["😏", "😜", "🙃", "👀", "😈"],
        "flirty": ["😘", "💋", "🔥", "😍", "🥵"],
        "tired": ["🥱", "😴", "💤", "😪"],
        "caring": ["❤️", "🥺", "💕", "🫶"],
        "sad": ["🥺", "😢", "💔"],
    }
    
    async def humanize_response(self, response: str, mood: str = "happy",
                                 user_message_length: int = 0) -> Tuple[List[str], float]:
        """Transform response to feel more human"""

        # Calculate typing delay
        delay = self._calculate_delay(response, user_message_length)

        text = response

        # Maybe add typo (6% chance)
        if random.random() < 0.06:
            text = self._add_typo(text)

        # Maybe add emoji (25% chance)
        if random.random() < 0.25:
            text = self._maybe_add_emoji(text, mood)

        # Casualize text
        text = self._casualize(text)

        # Maybe split into multiple messages (35% for long messages)
        messages = self._maybe_split(text)

        return messages, delay

    async def humanize_text(self, text: str, mood: str = "happy") -> str:
        """Humanize a single text message (for use with realistic_delays)"""

        # Maybe add typo (6% chance)
        if random.random() < 0.06:
            text = self._add_typo(text)

        # Maybe add visible correction (4% chance)
        if random.random() < 0.04:
            text = self._add_visible_correction(text)

        # Maybe add emoji (20% chance)
        if random.random() < 0.20:
            text = self._maybe_add_emoji(text, mood)

        # Casualize
        text = self._casualize(text)

        return text

    def _add_visible_correction(self, text: str) -> str:
        """Add visible correction like a real human. Ex: 'i lovw' → 'love*'"""
        words = text.split()
        if len(words) < 3:
            return text

        idx = random.randint(1, min(4, len(words) - 1))
        word = words[idx]

        if len(word) < 4:
            return text

        correction_types = [
            lambda w: w[:2] + w[3] + w[2] + w[4:] if len(w) > 4 else w,
            lambda w: w[:len(w)//2] + w[len(w)//2+1:],
            lambda w: w[:2] + w[2] + w[2:],
        ]

        try:
            typo_word = random.choice(correction_types)(word)
            if typo_word != word:
                words[idx] = typo_word
                words.insert(idx + 1, f"{word}*")
        except:
            pass

        return " ".join(words)

    def maybe_create_interrupted_message(self, text: str, mood: str) -> Tuple[List[str], bool]:
        """Sometimes Luna interrupts herself. Returns (messages, was_interrupted)"""
        if random.random() > 0.03 or len(text) < 30:
            return [text], False

        interrupt_patterns = [
            {"cut": lambda t: t[:len(t)//3] + "...", "followup": lambda t: "sorry " + t},
            {"cut": lambda t: t[:len(t)//4] + "-", "followup": lambda t: "wait, " + t},
            {"cut": lambda t: t[:len(t)//3], "followup": lambda t: "anyway " + t[len(t)//3:]},
            {"cut": "hold on", "followup": lambda t: t},
            {"cut": lambda t: "actually " + t[:len(t)//4] + "...", "followup": lambda t: "nvm lol"},
        ]

        pattern = random.choice(interrupt_patterns)
        cut = pattern["cut"](text) if callable(pattern["cut"]) else pattern["cut"]
        followup = pattern["followup"](text) if callable(pattern["followup"]) else pattern["followup"]

        return [cut, followup], True

    def maybe_add_stutter_hesitation(self, text: str) -> str:
        """Sometimes add natural hesitations."""
        if random.random() > 0.08:
            return text

        hesitations_start = ["um ", "like ", "idk ", "well ", "so "]
        hesitations_middle = [" like ", " you know ", " idk ", " kinda "]

        if random.random() < 0.6:
            text = random.choice(hesitations_start) + text.lstrip()
        else:
            words = text.split()
            if len(words) > 4:
                mid = len(words) // 2
                words.insert(mid, random.choice(hesitations_middle).strip())
                text = " ".join(words)

        return text

    def _calculate_delay(self, response: str, user_len: int) -> float:
        """Calculate realistic typing delay"""
        words = len(response.split())
        
        if words < 10:
            delay = random.uniform(2.0, 4.0)
        elif words < 25:
            delay = random.uniform(4.0, 7.0)
        else:
            delay = random.uniform(6.0, 10.0)
        
        # Longer delay if user sent long message (reading time)
        if user_len > 100:
            delay += 1.5
        
        # Late night = slower
        hour = datetime.now().hour
        if hour >= 23 or hour < 7:
            delay *= 1.3
        
        return min(delay, 12.0)
    
    def _add_typo(self, text: str) -> str:
        """Add realistic typo with autocorrect"""
        words = text.split()
        if len(words) < 3:
            return text
        
        idx = random.randint(1, len(words) - 1)
        word = words[idx]
        
        if len(word) < 3:
            return text
        
        char_idx = random.randint(0, len(word) - 1)
        char = word[char_idx].lower()
        
        if char in self.TYPO_REPLACEMENTS:
            typo = random.choice(self.TYPO_REPLACEMENTS[char])
            typo_word = word[:char_idx] + typo + word[char_idx + 1:]
            
            # 70% chance to autocorrect
            if random.random() < 0.7:
                words[idx] = f"{typo_word}* {word}"
            else:
                words[idx] = typo_word
        
        return " ".join(words)
    
    def _maybe_add_emoji(self, text: str, mood: str) -> str:
        """Add mood-appropriate emoji"""
        emojis = self.MOOD_EMOJIS.get(mood, self.MOOD_EMOJIS["happy"])
        return text + " " + random.choice(emojis)
    
    def _casualize(self, text: str) -> str:
        """Make text more casual"""
        
        # Random lowercase (30% chance for short messages)
        if random.random() < 0.3 and len(text) < 60:
            text = text.lower()
        
        # Remove trailing punctuation sometimes
        if random.random() < 0.25:
            text = text.rstrip('.!')
        
        # Casual replacements (40% chance each)
        replacements = [
            (r'\byou\b', 'u'),
            (r'\bare\b', 'r'),
            (r'\bwant to\b', 'wanna'),
            (r'\bgoing to\b', 'gonna'),
            (r'\bkind of\b', 'kinda'),
            (r'\bI don\'t know\b', 'idk'),
            (r'\bto be honest\b', 'tbh'),
            (r'\bnot gonna lie\b', 'ngl'),
            (r'\bright now\b', 'rn'),
            (r'\boh my god\b', 'omg'),
        ]
        
        for pattern, repl in replacements:
            if random.random() < 0.4:
                text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        
        return text
    
    def _maybe_split(self, text: str) -> List[str]:
        """Maybe split into multiple messages"""
        
        if len(text) < 70 or random.random() > 0.35:
            return [text]
        
        # Split on sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        if len(sentences) < 2:
            return [text]
        
        mid = len(sentences) // 2
        return [" ".join(sentences[:mid]), " ".join(sentences[mid:])]


humanizer_en = HumanizerService()
