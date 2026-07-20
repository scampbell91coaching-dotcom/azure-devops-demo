from flask import Flask, jsonify
import socket

app = Flask(__name__)

@app.get("/")
def home():
    return jsonify(
        status="ok",
        host=socket.gethostname(),
        message="Flask app is running"
    )

@app.get("/health")
def health():
    return jsonify(status="healthy"), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
