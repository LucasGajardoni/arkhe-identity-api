from pathlib import Path
from urllib.request import urlretrieve

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}


def main() -> None:
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    for filename, url in MODELS.items():
        target = models_dir / filename
        if target.exists() and target.stat().st_size > 0:
            print(f"Already exists: {target}")
            continue
        print(f"Downloading {filename}")
        urlretrieve(url, target)  # noqa: S310
        print(f"Saved {target}")


if __name__ == "__main__":
    main()
