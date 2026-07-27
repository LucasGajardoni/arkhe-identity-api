$ErrorActionPreference = "Stop"
$models = Join-Path (Get-Location) "models"
New-Item -ItemType Directory -Force -Path $models | Out-Null

$files = @(
  @{
    Url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    Out = "face_detection_yunet_2023mar.onnx"
  },
  @{
    Url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    Out = "face_recognition_sface_2021dec.onnx"
  }
)

foreach ($file in $files) {
  $target = Join-Path $models $file.Out
  Invoke-WebRequest -Uri $file.Url -OutFile $target
  Write-Host "Downloaded $target"
}
