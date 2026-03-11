from ultralytics import YOLO

# Load the PyTorch model
model = YOLO("model/yolo8_best.pt")

# Export the model to ONNX format
# imgsz=320 makes the model much smaller and faster for Render's free tier
model.export(format="onnx", imgsz=320)

print("\nSuccess! 'model/yolo8_best.onnx' has been created.")
print("Now push this file to your GitHub repository.")
