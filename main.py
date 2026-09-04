"""this is my first attempt at creating a virtual assistant named Jarvis.
 it can  perform various tasks such as opening websites like youtube and all"""
import speech_recognition as sr
import webbrowser
import pyttsx3
import music_library
import requests
import pygame
from gtts import gTTS
import os
from dotenv import load_dotenv

# pip install pocketsphinx

# Initialize Speech Recognition and Text-to-Speech
load_dotenv()
recognizer = sr.Recognizer()
newsapi = os.getenv("NEWS_API_KEY")


def speak_old(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


pygame.mixer.init()


def speak(text):
    tts = gTTS(text=text, lang='en')
    tts.save("temp.mp3")

    pygame.mixer.music.load("temp.mp3")
    pygame.mixer.music.play()

    # Wait until the speech finishes
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    # Clean up the temporary file
    pygame.mixer.music.unload()
    os.remove("temp.mp3")


def process_command(c):

    if c.lower() == "open youtube":
        webbrowser.open("https://www.youtube.com")
        speak("Opening YouTube")

    elif "open google" in c.lower():
        webbrowser.open("https://www.google.com")
        speak("Opening Google")

    elif "open facebook" in c.lower():
        webbrowser.open("https://www.facebook.com")
        speak("Opening Facebook")

    elif "open instagram" in c.lower():
        webbrowser.open("https://www.instagram.com")
        speak("Opening Instagram")

    elif "open linkedin" in c.lower():
        webbrowser.open("https://www.linkedin.com")
        speak("Opening LinkedIn")

    elif c.lower().startswith("play"):
        song = c.lower().split(" ")[1]
        link = music_library.music[song]
        webbrowser.open(link)
        speak(f"Playing {song}")

    elif "news" in c.lower():
        r = requests.get(
            f"https://newsapi.org/v2/top-headlines"
            f"?country=in&apiKey={newsapi}"
        )

        if r.status_code == 200:
            data = r.json()
            articles = data.get("articles", [])

            for article in articles:  # Get top 5 news articles
                speak(article["title"])

    else:
        # let open ai handle the command
        speak("I am sorry, I cannot handle that command yet.")


if __name__ == "__main__":

    speak("Initializing Jarvis...")

    while True:

        # Recognize speech using Google Speech Recognition
        r = sr.Recognizer()

        print("Recognizing...")

        try:

            # Listen for audio from the microphone
            with sr.Microphone() as source:

                print("Listening...")

                audio = r.listen(
                    source,
                    timeout=2,
                    phrase_time_limit=3
                )

            word = r.recognize_google(audio)

            print("You said: " + word)

            if word.lower() == "jarvis":

                speak("Yes boss")

                # Listen for the next command
                with sr.Microphone() as source:

                    print("Activated jarvis...")

                    audio = r.listen(
                        source,
                        timeout=2,
                        phrase_time_limit=5
                    )

                    command = r.recognize_google(audio)

                    process_command(command)

        except Exception as e:

            print("Error; {0}".format(e))