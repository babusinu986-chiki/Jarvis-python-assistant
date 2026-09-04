"""This is my first attempt at creating a virtual assistant named Jarvis. It can perform various tasks such as opening websites,
 playing music, and fetching news headlines. The assistant listens for specific wake words to activate and can remember user 
 preferences using a simple memory system."""

"""The code is written by me with the help of ai like gpt and claude. 
i take a challange to create a new project everyday and pot it here """
# ===========================
# Have a nice journey to see my code and learn from it. if you have any question then you can ask me on my email: babusinu997@gmail.com
#  ==========================

import random
import json
import os
import traceback
import speech_recognition as sr
import webbrowser
import pyttsx3
import music_library
import requests
import pygame
from gtts import gTTS
from dotenv import load_dotenv



# =========================
# INITIALIZATION
# =========================
load_dotenv()

recognizer = sr.Recognizer()


newsapi = os.getenv("NEWS_API_KEY")  # Replace with your actual News API key

wake_words = [
    "hay bro",
    "jarvis",
    "hey jarvis",
    "ok jarvis",
    "wake up jarvis",
    "hello jarvis"
]

responses = [
    "Yes boss",
    "hukum doo",
    "spit it out",
    "Ready when you are",
    "What can I do for you?",
    "Systems online"
]

MEMORY_FILE = "memory.json"


# =========================
# MEMORY SYSTEM
# =========================

def initialize_memory():

    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w") as file:
            json.dump({}, file, indent=4)


def save_memory(key, value):
    initialize_memory()

    with open(MEMORY_FILE, "r") as file:
        memory = json.load(file)

    memory[key] = value

    with open(MEMORY_FILE, "w") as file:
        json.dump(memory, file, indent=4)


def get_memory(key):
    initialize_memory()

    with open(MEMORY_FILE, "r") as file:
        memory = json.load(file)

    return memory.get(key)


# =========================
# TEXT TO SPEECH
# =========================

def speak_old(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


pygame.mixer.init()


def speak(text):

    temp_file = "temp.mp3"

    try:
        tts = gTTS(text=text, lang="en")
        tts.save(temp_file)

        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

    finally:
        try:
            pygame.mixer.music.unload()
        except pygame.error:
            pass

        if os.path.exists(temp_file):
            os.remove(temp_file)


# =========================
# COMMAND PROCESSOR
# =========================

def process_command(command):
    command = command.lower().strip()

    # -------------------------
    # MEMORY COMMANDS
    # -------------------------

    if "what is my name" in command:
        name = get_memory("name")

        if name:
            speak(f"Your name is {name}")
        else:
            speak("I do not know your name yet, boss.")

    elif command.startswith("remember my name is "):
        name = command.replace("remember my name is ", "", 1).strip()

        if name:
            save_memory("name", name)
            speak(f"I will remember your name as {name}, boss.")

    elif "what is my favorite song" in command:
        song = get_memory("favorite_song")

        if song:
            speak(f"Your favorite song is {song}")
        else:
            speak("You have not told me your favorite song yet.")

    elif command.startswith("remember my favorite song is "):
        song = command.replace(
            "remember my favorite song is ", "" ,1).strip()

        if song:
            save_memory("favorite_song", song)
            speak(f"I will remember your favorite song as {song}.")

    # -------------------------
    # WEBSITE COMMANDS
    # -------------------------

    elif "open youtube" in command:
        webbrowser.open("https://www.youtube.com")
        speak("Opening YouTube")

    elif "open google" in command:
        webbrowser.open("https://www.google.com")
        speak("Opening Google")

    elif "open facebook" in command:
        webbrowser.open("https://www.facebook.com")
        speak("Opening Facebook")

    elif "open instagram" in command:
        webbrowser.open("https://www.instagram.com")
        speak("Opening Instagram")

    elif "open linkedin" in command:
        webbrowser.open("https://www.linkedin.com")
        speak("Opening LinkedIn")

    # -------------------------
    # MUSIC COMMAND
    # -------------------------

    elif command.startswith("play "):
        song = command.replace("play ", "", 1).strip()

        if song in music_library.music:
            link = music_library.music[song]
            webbrowser.open(link)
            speak(f"Playing {song}")
        else:
            speak("Sorry boss, that song is not in your music library.")

    # -------------------------
    # NEWS COMMAND
    # -------------------------

    elif "news" in command:
        try:
            response = requests.get(
                f"https://newsapi.org/v2/top-headlines"
                f"?country=in&apiKey={newsapi}",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                articles = data.get("articles", [])

                if not articles:
                    speak("Sorry boss, no news was found.")
                    return

                for article in articles[:5]:
                    title = article.get("title")

                    if title:
                        speak(title)
            else:
                speak("Sorry boss, I could not fetch the news.")

        except requests.RequestException:
            speak("There was a problem connecting to the news service.")

    # -------------------------
    # UNKNOWN COMMAND
    # -------------------------

    else:
        speak("I am sorry, I cannot handle that command yet.")


# =========================
# MAIN PROGRAM
# =========================

if __name__ == "__main__":

    initialize_memory()

    speak("Initializing Jarvis...")

    active = False

    with sr.Microphone() as source:
        print("Calibrating microphone for background noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    print("Jarvis is ready.")

    while True:
        try:
            # =========================
            # SLEEP MODE
            # =========================

            if not active:
                print("Listening for wake word...")

                with sr.Microphone() as source:
                    audio = recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=4
                    )

                word = recognizer.recognize_google(audio)

                print("You said:", word)

                if any(
                    wake_word in word.lower()
                    for wake_word in wake_words
                ):
                    active = True
                    speak(random.choice(responses))

            # =========================
            # ACTIVE MODE
            # =========================

            else:
                print("Listening for command...")

                with sr.Microphone() as source:
                    audio = recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=7
                    )

                command = recognizer.recognize_google(audio)

                print("Command:", command)

                command = command.lower().strip()

                if command == "sleep":
                    active = False
                    speak("Going to sleep mode")

                elif command in ["exit", "quit", "shutdown"]:
                    speak("Goodbye boss")
                    break

                else:
                    process_command(command)

        except sr.WaitTimeoutError:
            print("No speech detected.")

        except sr.UnknownValueError:
            print("Sorry, I could not understand the audio.")

        except sr.RequestError:
            print("Speech recognition service is unavailable.")

        except KeyboardInterrupt:
            print("\nJarvis stopped.")
            break

        except Exception:
            traceback.print_exc()
''' note kario ak bar command run hone ke baad firse tujhe jarvis bolke start karne padega then j bhi bol sata hei '''
