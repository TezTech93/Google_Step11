import os
import io
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from PIL import Image
from typing import Optional

app = FastAPI(title="Image Resizer API")

# HTML template (embedded for simplicity)
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Image Resizer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 600px; margin: auto; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        input, select { width: 100%; padding: 8px; margin-top: 5px; }
        button { margin-top: 20px; padding: 10px 20px; background-color: #4CAF50; color: white; border: none; cursor: pointer; }
        button:hover { background-color: #45a049; }
        .info { background-color: #e7f3fe; padding: 10px; margin-top: 20px; border-left: 6px solid #2196F3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🖼️ Image Resizer</h1>
        <div class="info">
            <strong>Instructions:</strong> Upload an image, choose resize settings, and download.
        </div>
        <form action="/resize" method="post" enctype="multipart/form-data">
            <label for="file">Select image:</label>
            <input type="file" name="file" accept="image/*" required>

            <label for="mode">Resize mode:</label>
            <select name="mode" id="mode" onchange="toggleInputs()">
                <option value="exact">Exact dimensions (width × height)</option>
                <option value="fit">Fit inside a box (keep aspect)</option>
                <option value="longest">Longest side (keep aspect)</option>
            </select>

            <div id="exact-inputs">
                <label for="width">Width (px):</label>
                <input type="number" name="width" value="800" min="1">
                <label for="height">Height (px):</label>
 <input type="number" name="height" value="600" min="1">
            </div>

            <div id="fit-inputs" style="display:none;">
                <label for="box_width">Box width (px):</label>
                <input type="number" name="box_width" value="300" min="1">
                <label for="box_height">Box height (px):</label>
                <input type="number" name="box_height" value="300" min="1">
            </div>

            <div id="longest-inputs" style="display:none;">
                <label for="longest">Longest side (px):</label>
                <input type="number" name="longest" value="500" min="1">
            </div>

            <label for="output_name">Output filename (without extension):</label>
            <input type="text" name="output_name" value="resized_image">

            <label for="output_format">Output format:</label>
            <select name="output_format">
                <option value="original">Same as input</option>
                <option value="JPEG">JPEG</option>
                <option value="PNG">PNG</option>
                <option value="GIF">GIF</option>
                <option value="BMP">BMP</option>
                <option value="WEBP">WebP</option>
            </select>

            <button type="submit">Resize & Download</button>
        </form>
    </div>

    <script>
        function toggleInputs() {
            const mode = document.getElementById('mode').value;
            document.getElementById('exact-inputs').style.display = mode === 'exact' ? 'block' : 'none';
            document.getElementById('fit-inputs').style.display = mode === 'fit' ? 'block' : 'none';
            document.getElementById('longest-inputs').style.display = mode === 'longest' ? 'block' : 'none';
        }
        // Set initial visibility
        toggleInputs();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return HTML_PAGE

@app.post("/resize")
async def resize_image(
    file: UploadFile = File(...),
    mode: str = Form(...),
    output_name: str = Form("resized_image"),
    output_format: str = Form("original"),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    box_width: Optional[int] = Form(None),
    box_height: Optional[int] = Form(None),
    longest: Optional[int] = Form(None)
):
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")

    # Open the image
    try:
        image = Image.open(file.file)
    except Exception:
        raise HTTPException(400, "Invalid image file")

    original_width, original_height = image.size

    # Determine target size based on mode
    if mode == "exact":
        if width is None or height is None:
            raise HTTPException(400, "Width and height are required for exact mode")
        new_width, new_height = width, height
    elif mode == "fit":
        if box_width is None or box_height is None:
            raise HTTPException(400, "Box dimensions required for fit mode")
        # Scale to fit inside the box while preserving aspect
        ratio = min(box_width / original_width, box_height / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)
    elif mode == "longest":
        if longest is None:
            raise HTTPException(400, "Longest side value required")
        # Scale so that the longer side becomes `longest`
        if original_width >= original_height:
            new_width = longest
            new_height = int((longest / original_width) * original_height)
        else:
            new_height = longest
            new_width = int((longest / original_height) * original_width)
    else:
        raise HTTPException(400, "Invalid resize mode")

    # Resize (using LANCZOS for high quality)
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Determine output format and MIME type
    fmt = output_format.upper()
    if fmt == "ORIGINAL":
        # Use original format, fallback to PNG if unknown
        fmt = image.format if image.format else "PNG"
    # Map format to MIME
    mime_types = {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "BMP": "image/bmp",
        "WEBP": "image/webp"
    }
    mime = mime_types.get(fmt.upper(), "application/octet-stream")

    # Save to bytes buffer
    buf = io.BytesIO()
    # Handle special cases: JPEG doesn't support alpha; convert to RGB if needed
    if fmt.upper() in ("JPEG", "JPG") and resized.mode in ("RGBA", "LA", "P"):
        # Create a white background and paste the image
        background = Image.new("RGB", resized.size, (255, 255, 255))
        if resized.mode == "P":
            resized = resized.convert("RGBA")
        background.paste(resized, mask=resized.split()[-1] if resized.mode == "RGBA" else None)
        resized = background
    elif fmt.upper() == "GIF" and resized.mode != "P":
        # Convert to palette for GIF
        resized = resized.convert("P", palette=Image.ADAPTIVE)

    resized.save(buf, format=fmt)
    buf.seek(0)

    # Determine file extension
    ext = fmt.lower()
    if ext == "jpeg":
        ext = "jpg"

    filename = f"{output_name}.{ext}"

    return StreamingResponse(buf, media_type=mime, headers={"Content-Disposition": f"attachment; filename={filename}"})