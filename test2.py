import sounddevice as sd
import soundfile as sf
data, fs = sf.read("/home/lelamp/lelampv2/assets/AudioFX/Effects/Scifi-PointCollected.wav")
sd.play(data, fs)
sd.wait()