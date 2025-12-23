import asyncio
import random
import re
from typing import List, Tuple
from datetime import datetime

class HumanizerServiceFR:
    """Makes Luna's responses feel human - French version"""
    
    # AZERTY keyboard typos
    TYPO_REPLACEMENTS = {
        'a': ['z', 'q'], 'e': ['r', 'z'], 'i': ['u', 'o'],
        'o': ['i', 'p'], 't': ['r', 'y'], 's': ['q', 'd'],
        'u': ['i', 'y'], 'n': ['b', 'h'], 'm': ['n', 'l']
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

        delay = self._calculate_delay(response, user_message_length)
        text = response

        if random.random() < 0.06:
            text = self._add_typo(text)

        if random.random() < 0.25:
            text = self._maybe_add_emoji(text, mood)

        text = self._casualize_fr(text)
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
        text = self._casualize_fr(text)

        return text

    def _add_visible_correction(self, text: str) -> str:
        """
        Ajoute une correction visible comme un vrai humain.
        Ex: "je t'aome" → "aime*"
        """
        words = text.split()
        if len(words) < 3:
            return text

        # Choisir un mot à "mal écrire" puis corriger
        idx = random.randint(1, min(4, len(words) - 1))
        word = words[idx]

        if len(word) < 4:
            return text

        # Types de corrections
        correction_types = [
            # Inversion de lettres
            lambda w: w[:2] + w[3] + w[2] + w[4:] if len(w) > 4 else w,
            # Lettre manquante
            lambda w: w[:len(w)//2] + w[len(w)//2+1:],
            # Double lettre
            lambda w: w[:2] + w[2] + w[2:],
        ]

        try:
            typo_word = random.choice(correction_types)(word)
            if typo_word != word:
                words[idx] = typo_word
                # Ajouter la correction après
                words.insert(idx + 1, f"{word}*")
        except:
            pass

        return " ".join(words)

    def maybe_create_interrupted_message(self, text: str, mood: str) -> Tuple[List[str], bool]:
        """
        Parfois Luna s'interrompt comme un vrai humain.
        Retourne (messages, was_interrupted)
        """
        # 3% chance d'interruption
        if random.random() > 0.03 or len(text) < 30:
            return [text], False

        interrupt_patterns = [
            # Message coupé puis reprise
            {
                "cut": lambda t: t[:len(t)//3] + "...",
                "followup": lambda t: "dsl " + t
            },
            # Commence puis "attends"
            {
                "cut": lambda t: t[:len(t)//4] + "-",
                "followup": lambda t: "pardon, " + t
            },
            # S'interrompt pour autre chose
            {
                "cut": lambda t: t[:len(t)//3],
                "followup": lambda t: "bref " + t[len(t)//3:]
            },
            # "attends" puis message complet
            {
                "cut": "attends",
                "followup": lambda t: t
            },
            # Pensée incomplète
            {
                "cut": lambda t: "en fait " + t[:len(t)//4] + "...",
                "followup": lambda t: "nan rien laisse mdr"
            },
        ]

        pattern = random.choice(interrupt_patterns)

        cut = pattern["cut"](text) if callable(pattern["cut"]) else pattern["cut"]
        followup = pattern["followup"](text) if callable(pattern["followup"]) else pattern["followup"]

        return [cut, followup], True

    def maybe_add_stutter_hesitation(self, text: str) -> str:
        """
        Ajoute parfois des hésitations naturelles.
        "je... je sais pas", "euh", "enfin"
        """
        if random.random() > 0.08:  # 8% chance
            return text

        hesitations_start = [
            "euh ",
            "hm ",
            "enfin ",
            "genre ",
            "bah ",
            "jsp ",
        ]

        hesitations_middle = [
            " enfin ",
            " genre ",
            " tu vois ",
            " quoi ",
        ]

        if random.random() < 0.6:
            # Hésitation au début
            text = random.choice(hesitations_start) + text.lstrip()
        else:
            # Hésitation au milieu
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
        
        if user_len > 100:
            delay += 1.5
        
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
            
            if random.random() < 0.7:
                words[idx] = f"{typo_word}* {word}"
            else:
                words[idx] = typo_word
        
        return " ".join(words)
    
    def _maybe_add_emoji(self, text: str, mood: str) -> str:
        """Add mood-appropriate emoji"""
        emojis = self.MOOD_EMOJIS.get(mood, self.MOOD_EMOJIS["happy"])
        return text + " " + random.choice(emojis)
    
    def _casualize_fr(self, text: str) -> str:
        """Make text more casual - French style"""
        
        if random.random() < 0.3 and len(text) < 60:
            text = text.lower()
        
        if random.random() < 0.25:
            text = text.rstrip('.!')
        
        # French casual replacements
        replacements = [
            (r'\bje suis\b', 'jsuis'),
            (r'\bje ne sais pas\b', 'jsp'),
            (r'\bje sais pas\b', 'jsp'),
            (r'\bc\'est\b', 'c'),
            (r'\bqu\'est-ce que\b', 'keske'),
            (r'\bpeut-être\b', 'ptetre'),
            (r'\bs\'il te plaît\b', 'stp'),
            (r'\btu es\b', 't\'es'),
            (r'\bje t\'aime\b', 'jtm'),
            (r'\bd\'accord\b', 'dac'),
            (r'\boui\b', 'ouais'),
            (r'\bnon\b', 'nan'),
            (r'\btrès\b', 'trop'),
            (r'\bbeaucoup\b', 'bcp'),
        ]
        
        for pattern, repl in replacements:
            if random.random() < 0.4:
                text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        
        return text
    
    def _maybe_split(self, text: str) -> List[str]:
        """Maybe split into multiple messages"""
        
        if len(text) < 70 or random.random() > 0.35:
            return [text]
        
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        if len(sentences) < 2:
            return [text]
        
        mid = len(sentences) // 2
        return [" ".join(sentences[:mid]), " ".join(sentences[mid:])]


humanizer_fr = HumanizerServiceFR()
