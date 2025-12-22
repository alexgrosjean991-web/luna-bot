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
