# curl -LsSf https://astral.sh/uv/install.sh | sh
# sudo apt install python3.13-dev
# sudo apt install swig
# sudo apt install portaudio19-dev
# uv sync
# ./install/install_python.sh --set-caps
# ./install/install_rgb.sh --pi5
'''
Fast language models are crucial in today's technological landscape, and their importance can be understood from several perspectives:

1. **Efficient Processing**: Fast language models can process and analyze vast amounts of natural language data quickly, making them ideal for applications that require real-time or near-real-time processing, such as chatbots, virtual assistants, and language translation systems.
2. **Improved User Experience**: Quick response times are essential for providing a seamless user experience, especially in customer-facing applications like customer service chatbots, language translation apps, and voice assistants. Fast language models enable these applications to respond rapidly, making interactions feel more natural and engaging.
3. **Scalability**: Fast language models can handle a large volume of requests and conversations simultaneously, making them suitable for large-scale applications, such as language translation platforms, social media monitoring, and content analysis.
4. **Energy Efficiency**: Faster language models can lead to significant energy savings, as they require less computational power and time to process requests. This is particularly important for applications that run on devices with limited power resources, such as smartphones and smart home devices.
5. **Competitive Advantage**: In the realm of natural language processing (NLP), having a fast language model can provide a competitive advantage. Organizations that leverage fast language models can respond more quickly to customer inquiries, provide faster language translation services, and gain an edge over competitors.
6. **Real-Time Insights**: Fast language models enable real-time analysis of large datasets, providing valuable insights and trends that can inform business decisions, predict market shifts, and identify potential issues before they become major problems.
7. **Edge Computing**: With the proliferation of edge computing, fast language models can be deployed on edge devices, such as smartphones, smart home devices, and autonomous vehicles, enabling real-time processing and reducing latency.
8. **Accessibility**: Fast language models can facilitate more efficient and effective communication for people with disabilities, such as those who rely on speech-to-text systems or language translation services.
9. **Multilingual Support**: Fast language models can support multiple languages, enabling organizations to provide services and communicate with customers in their native languages, regardless of geographical location.
10. **Advancements in NLP Research**: The development of fast language models drives innovation in NLP research, pushing the boundaries of what is possible and enabling the creation of more sophisticated language models that can tackle complex tasks and applications.

To achieve fast language models, researchers and developers employ various techniques, such as:

* Model pruning and quantization
* Knowledge distillation
* Efficient attention mechanisms
* Hardware acceleration (e.g., GPUs, TPUs)
* Parallel processing and distributed computing
* Pre-training and fine-tuning of models

By focusing on speed and efficiency, language model developers can create more effective, scalable, and accessible NLP systems that can be applied to a wide range of applications, from customer service and language translation to content analysis and real-time insights.
'''
import sounddevice as sd
print(sd.query_devices())
import numpy as np

def run_audio_test():
    # --- 配置参数 ---
    fs = 16000  # 采样率 (Hz)，44100 是标准 CD 音质
    duration = 5  # 录音时长 (秒)
    channels = 1  # 声道数 (1=单声道, 2=立体声)

    print(f"准备开始... 请对着麦克风说话。")
    print(f"正在录音 ({duration} 秒)...")

    # --- 1. 录音 ---
    # sd.rec(帧数, 采样率, 声道)
    # 帧数 = 时长 * 采样率
    myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=channels, dtype='int16')

    # sd.rec 是非阻塞的（后台运行），所以我们需要调用 wait() 来暂停程序直到录音结束
    sd.wait()

    print("录音结束！")
    print("-" * 20)
    print("正在播放录制的声音...")
    num_samples_out = int(len(myrecording) * 48000 / 16000)
    from scipy import signal

    # 使用 scipy.signal.resample 进行重采样
    # 注意: resample 接受的必须是数组
    resampled_data = signal.resample(myrecording, num_samples_out)

    # --- 2. 播放 ---
    # sd.play(数据, 采样率)
    sd.play(resampled_data)

    #同样，sd.play 也是非阻塞的，需要 wait() 等待播放完成
    sd.wait()

    print("播放结束！")

if __name__ == "__main__":
    try:
        run_audio_test()
    except Exception as e:
        print(f"发生错误: {e}")
        print("请检查麦克风设置或是否安装了 PortAudio。")
