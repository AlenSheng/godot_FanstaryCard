param(
    [Parameter(Mandatory = $true)] [string] $FrameOffSource,
    [Parameter(Mandatory = $true)] [string] $FrameOnSource,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot "..\client\assets\imported\UI\Hall")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

function Test-CheckerPixel([System.Drawing.Color] $Color) {
    # Generated frame previews use a neutral light checkerboard outside the card.
    # The fill is removed only when it is contiguous with an image edge, preserving
    # the dark teal card interior and anti-aliased perimeter.
    $spread = [Math]::Max($Color.R, [Math]::Max($Color.G, $Color.B)) - [Math]::Min($Color.R, [Math]::Min($Color.G, $Color.B))
    $lightChecker = $Color.R -ge 140 -and $Color.G -ge 140 -and $Color.B -ge 140 -and $spread -le 26
    # The image service occasionally flattens the transparent preview outside
    # the checkerboard into opaque black. Treat only edge-connected near-black
    # pixels as background so the inner dark teal panel is not affected.
    $flattenedTransparentBlack = $Color.R -le 10 -and $Color.G -le 10 -and $Color.B -le 10
    return $lightChecker -or $flattenedTransparentBlack
}

function Clear-OuterCheckerboard([System.Drawing.Bitmap] $Bitmap) {
    $width = $Bitmap.Width
    $height = $Bitmap.Height
    $visited = New-Object 'bool[,]' $width, $height
    $queue = [System.Collections.Generic.Queue[System.Drawing.Point]]::new()

    function Enqueue-If-Background([int] $X, [int] $Y) {
        if ($X -lt 0 -or $Y -lt 0 -or $X -ge $width -or $Y -ge $height -or $visited[$X, $Y]) { return }
        if (-not (Test-CheckerPixel $Bitmap.GetPixel($X, $Y))) { return }
        $visited[$X, $Y] = $true
        $queue.Enqueue([System.Drawing.Point]::new($X, $Y))
    }

    for ($x = 0; $x -lt $width; $x++) {
        Enqueue-If-Background $x 0
        Enqueue-If-Background $x ($height - 1)
    }
    for ($y = 0; $y -lt $height; $y++) {
        Enqueue-If-Background 0 $y
        Enqueue-If-Background ($width - 1) $y
    }

    while ($queue.Count -gt 0) {
        $point = $queue.Dequeue()
        $Bitmap.SetPixel($point.X, $point.Y, [System.Drawing.Color]::FromArgb(0, 0, 0, 0))
        Enqueue-If-Background ($point.X - 1) $point.Y
        Enqueue-If-Background ($point.X + 1) $point.Y
        Enqueue-If-Background $point.X ($point.Y - 1)
        Enqueue-If-Background $point.X ($point.Y + 1)
    }
}

function Export-Frame([string] $Source, [string] $Destination) {
    $input = [System.Drawing.Bitmap]::new($Source)
    try {
        Clear-OuterCheckerboard $input
        $output = [System.Drawing.Bitmap]::new(928, 432, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($output)
            try {
                $graphics.Clear([System.Drawing.Color]::Transparent)
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.DrawImage($input, [System.Drawing.Rectangle]::new(0, 0, 928, 432))
            } finally { $graphics.Dispose() }
            # Bicubic resizing may recreate a near-black, partially opaque fringe
            # from fully transparent pixels. Remove that edge-connected fringe.
            Clear-OuterCheckerboard $output
            $output.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $output.Dispose() }
    } finally { $input.Dispose() }
}

function Export-Portrait([string] $HeroClass) {
    $source = Join-Path $PSScriptRoot "..\client\assets\imported\UI\Prep\exploration_prep_hero_portrait_$($HeroClass.ToLower()).png"
    $destination = Join-Path $OutputDirectory "class_card_portrait_$($HeroClass.ToLower()).png"
    $input = [System.Drawing.Bitmap]::new($source)
    try {
        $output = [System.Drawing.Bitmap]::new(256, 256, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($output)
            try {
                $graphics.Clear([System.Drawing.Color]::Transparent)
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                # Crop the transparent full-body art to the head-and-shoulders region used by the hall card.
                $graphics.DrawImage($input, [System.Drawing.Rectangle]::new(0, 0, 256, 256), [System.Drawing.Rectangle]::new(0, 0, 512, 512), [System.Drawing.GraphicsUnit]::Pixel)
            } finally { $graphics.Dispose() }
            $output.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $output.Dispose() }
    } finally { $input.Dispose() }
}

function Export-Heart {
    $destination = Join-Path $OutputDirectory "class_card_heart.png"
    $output = [System.Drawing.Bitmap]::new(64, 64, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($output)
        try {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
            $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
            $path.StartFigure()
            $path.AddBezier(32, 54, 14, 43, 7, 29, 13, 18)
            $path.AddBezier(13, 18, 17, 9, 28, 10, 32, 20)
            $path.AddBezier(32, 20, 36, 10, 47, 9, 51, 18)
            $path.AddBezier(51, 18, 57, 29, 50, 43, 32, 54)
            $path.CloseFigure()
            $shadow = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(145, 48, 8, 8))
            $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new([System.Drawing.Point]::new(20, 13), [System.Drawing.Point]::new(41, 54), [System.Drawing.Color]::FromArgb(255, 246, 84, 71), [System.Drawing.Color]::FromArgb(255, 154, 20, 24))
            $outline = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 88, 10, 14), 3)
            try {
                $graphics.TranslateTransform(0, 2)
                $graphics.FillPath($shadow, $path)
                $graphics.ResetTransform()
                $graphics.FillPath($fill, $path)
                $graphics.DrawPath($outline, $path)
            } finally {
                $shadow.Dispose()
                $fill.Dispose()
                $outline.Dispose()
                $path.Dispose()
            }
        } finally { $graphics.Dispose() }
        $output.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $output.Dispose() }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
Export-Frame $FrameOffSource (Join-Path $OutputDirectory "class_card_frame_off.png")
Export-Frame $FrameOnSource (Join-Path $OutputDirectory "class_card_frame_on.png")
foreach ($heroClass in "Priest", "Mage", "Guardian") { Export-Portrait $heroClass }
Export-Heart
