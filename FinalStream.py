from flask import Flask, Response, jsonify
import gi
import numpy as np
import cv2

gi.require_version('Gst', '1.0')
from gi.repository import Gst

app = Flask(__name__)

# Initialize GStreamer
Gst.init(None)

# Define the GStreamer pipeline
pipeline_string = (
    "avfvideosrc ! videoconvert ! video/x-raw,format=YUY2,width=1280,height=720 ! appsink name=appsink"
)
pipeline = Gst.parse_launch(pipeline_string)
appsink = pipeline.get_by_name("appsink")
appsink.set_property("emit-signals", True)
appsink.set_property("sync", False)
pipeline.set_state(Gst.State.PLAYING)

# Flags for streaming and recording
streaming = False
recording = False

# VideoWriter object
video_writer = None
output_file = "recorded_video.avi"
frame_width, frame_height = 1280, 720
fps = 30  # Frames per second

def generate_frames():
    global video_writer
    while True:
        if not streaming:
            break

        # Pull the latest sample from the appsink
        sample = appsink.emit("pull-sample")
        if not sample:
            break

        buffer = sample.get_buffer()
        caps = sample.get_caps()
        height = caps.get_structure(0).get_value("height")
        width = caps.get_structure(0).get_value("width")

        # Map the buffer to extract data
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            continue

        frame_data = np.frombuffer(map_info.data, dtype=np.uint8)
        buffer.unmap(map_info)

        # Convert YUY2 to BGR using OpenCV
        frame = frame_data.reshape((height, width, 2))
        frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_YUY2)

        # Convert to grayscale for recording
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Save the frame to the video file if recording
        if recording:
            if video_writer is None:
                # Initialize VideoWriter when recording starts
                fourcc = cv2.VideoWriter_fourcc(*'M', 'J', 'P', 'G')
                video_writer = cv2.VideoWriter(output_file, fourcc, fps, (width, height), True)
            video_writer.write(frame)

        # Encode the frame in JPEG format for streaming
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        # Yield the frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/start_stream', methods=['POST'])
def start_stream():
    global streaming
    streaming = True
    return jsonify({'message': 'Streaming started.'})

@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    global streaming, video_writer
    streaming = False
    # Release the video writer when streaming stops
    if video_writer:
        video_writer.release()
        video_writer = None
    return jsonify({'message': 'Streaming stopped.'})

@app.route('/start_recording', methods=['POST'])
def start_recording():
    global recording
    recording = True
    return jsonify({'message': 'Recording started.'})

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    global recording, video_writer
    recording = False
    # Release the video writer when recording stops
    if video_writer:
        video_writer.release()
        video_writer = None
    return jsonify({'message': 'Recording stopped and video saved.'})

@app.route('/video_feed')
def video_feed():
    global streaming
    if streaming:
        return Response(generate_frames(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return "Streaming is stopped", 200

@app.route('/')
def index():
    return '''
    <html>
    <head><title>Live Video Stream</title></head>
    <style>
            body {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                font-family: Arial, sans-serif;
                background-color: #f4f4f9;
            }
            h1 {
                margin-bottom: 20px;
                color: #333;
            }
            img {
                border: 2px solid #ccc;
                border-radius: 10px;
            }
    </style>
    <body>
        <h1>Live Video Feed from Webcam</h1>
        <img src="/video_feed">
        <div>
            <button onclick="controlStream('start_stream')">Start Streaming</button>
            <button onclick="controlStream('stop_stream')">Stop Streaming</button>
            <button onclick="controlStream('start_recording')">Start Recording</button>
            <button onclick="controlStream('stop_recording')">Stop Recording</button>
        </div>
        <script>
            function controlStream(action) {
                fetch(`/${action}`, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        console.log(data.message);
                        if (action === 'start_recording') {
                        // Display a confirmation message dynamically for "Start Recording"
                            const messageDiv = document.getElementById("status-message");
                            messageDiv.innerText = data.message; // Update the message dynamically
                            messageDiv.style.display = "block"; // Make the message visible
                        } else {
                        // Reload the page for other actions
                            window.location.reload();
                    }
                    })
                .catch(error => console.error('Error:', error));
            }
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5001, debug=False)
    finally:
        pipeline.set_state(Gst.State.NULL)
        if video_writer:
            video_writer.release()
