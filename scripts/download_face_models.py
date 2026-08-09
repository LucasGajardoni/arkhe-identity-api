from pathlib import Path
from urllib.request import urlretrieve

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        100_000,
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        10_000_000,
    ),
}


def main() -> None:
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    for filename, (url, minimum_size) in MODELS.items():
        target = models_dir / filename
        if target.exists() and target.stat().st_size >= minimum_size:
            print(f"Already exists: {target}")
            continue
        temporary = target.with_suffix(target.suffix + ".download")
        print(f"Downloading {filename}")
        urlretrieve(url, temporary)  # noqa: S310
        if temporary.stat().st_size < minimum_size:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded model is unexpectedly small: {filename}")
        temporary.replace(target)
        print(f"Saved {target}")


if __name__ == "__main__":
    main()
