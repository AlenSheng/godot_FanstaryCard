param(
    [Parameter(Mandatory = $true)] [string] $PortalSource,
    [Parameter(Mandatory = $true)] [string] $EntryBackgroundSource,
    [Parameter(Mandatory = $true)] [string] $EntryFrameSource,
    [Parameter(Mandatory = $true)] [string] $MarketIconSource,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot "..\client\assets\imported\UI\Hall")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

function Is-NearBlack([System.Drawing.Color] $Color) {
    return $Color.R -le 16 -and $Color.G -le 16 -and $Color.B -le 16
}

function Clear-NearBlackRegion([System.Drawing.Bitmap] $Bitmap, [System.Drawing.Point[]] $Seeds) {
    $width = $Bitmap.Width; $height = $Bitmap.Height
    $visited = New-Object 'bool[,]' $width, $height
    $queue = [System.Collections.Generic.Queue[System.Drawing.Point]]::new()
    function Add-Seed([int] $X, [int] $Y) {
        if ($X -lt 0 -or $Y -lt 0 -or $X -ge $width -or $Y -ge $height -or $visited[$X, $Y]) { return }
        if (-not (Is-NearBlack $Bitmap.GetPixel($X, $Y))) { return }
        $visited[$X, $Y] = $true; $queue.Enqueue([System.Drawing.Point]::new($X, $Y))
    }
    foreach ($seed in $Seeds) { Add-Seed $seed.X $seed.Y }
    while ($queue.Count -gt 0) {
        $point = $queue.Dequeue()
        $Bitmap.SetPixel($point.X, $point.Y, [System.Drawing.Color]::FromArgb(0, 0, 0, 0))
        Add-Seed ($point.X - 1) $point.Y; Add-Seed ($point.X + 1) $point.Y
        Add-Seed $point.X ($point.Y - 1); Add-Seed $point.X ($point.Y + 1)
    }
}

function Save-Scaled([System.Drawing.Bitmap] $Source, [string] $Destination, [int] $Width, [int] $Height, [System.Drawing.Rectangle] $Crop) {
    $output = [System.Drawing.Bitmap]::new($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($output)
        try {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($Source, [System.Drawing.Rectangle]::new(0, 0, $Width, $Height), $Crop, [System.Drawing.GraphicsUnit]::Pixel)
        } finally { $graphics.Dispose() }
        $output.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $output.Dispose() }
}

function Export-Portal([string] $Source) {
    $input = [System.Drawing.Bitmap]::new($Source)
    try { Save-Scaled $input (Join-Path $OutputDirectory "portal_background_clean.png") 835 550 ([System.Drawing.Rectangle]::new(0, 345, $input.Width, 675)) } finally { $input.Dispose() }
}

function Export-EntryBackground([string] $Source) {
    $input = [System.Drawing.Bitmap]::new($Source)
    try { Save-Scaled $input (Join-Path $OutputDirectory "entry_background.png") 256 256 ([System.Drawing.Rectangle]::new(0, 0, $input.Width, $input.Height)) } finally { $input.Dispose() }
}

function Export-EntryFrame([string] $Source) {
    $input = [System.Drawing.Bitmap]::new($Source)
    try {
        $destination = Join-Path $OutputDirectory "entry_frame.png"
        Save-Scaled $input $destination 256 256 ([System.Drawing.Rectangle]::new(0, 0, $input.Width, $input.Height))
        $output = [System.Drawing.Bitmap]::new($destination)
        $temporary = "$destination.tmp.png"
        try {
            $seeds = @([System.Drawing.Point]::new(0, 0), [System.Drawing.Point]::new($output.Width - 1, 0), [System.Drawing.Point]::new(0, $output.Height - 1), [System.Drawing.Point]::new($output.Width - 1, $output.Height - 1), [System.Drawing.Point]::new([int]($output.Width / 2), [int]($output.Height / 2)))
            Clear-NearBlackRegion $output $seeds
            $output.Save($temporary, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $output.Dispose() }
        Remove-Item -LiteralPath $destination -Force
        Move-Item -LiteralPath $temporary -Destination $destination
    } finally { $input.Dispose() }
}

function Export-MarketIcon([string] $Source) {
    $input = [System.Drawing.Bitmap]::new($Source)
    try {
        $destination = Join-Path $OutputDirectory "entry_icon_market.png"
        Save-Scaled $input $destination 256 256 ([System.Drawing.Rectangle]::new(0, 0, $input.Width, $input.Height))
        $output = [System.Drawing.Bitmap]::new($destination)
        $temporary = "$destination.tmp.png"
        try {
            $seeds = @([System.Drawing.Point]::new(0, 0), [System.Drawing.Point]::new($output.Width - 1, 0), [System.Drawing.Point]::new(0, $output.Height - 1), [System.Drawing.Point]::new($output.Width - 1, $output.Height - 1))
            Clear-NearBlackRegion $output $seeds
            $output.Save($temporary, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $output.Dispose() }
        Remove-Item -LiteralPath $destination -Force
        Move-Item -LiteralPath $temporary -Destination $destination
    } finally { $input.Dispose() }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
Export-Portal $PortalSource
Export-EntryBackground $EntryBackgroundSource
Export-EntryFrame $EntryFrameSource
Export-MarketIcon $MarketIconSource
