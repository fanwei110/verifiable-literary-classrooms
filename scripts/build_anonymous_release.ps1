param(
    [string]$PackageName = "Paper_A_anonymous_release"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RootFull = [System.IO.Path]::GetFullPath($Root.Path)
$Dest = Join-Path $RootFull "submission_package\$PackageName"
$DestFull = [System.IO.Path]::GetFullPath($Dest)

if (-not $DestFull.StartsWith($RootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination is outside project root: $DestFull"
}

if (Test-Path -LiteralPath $DestFull) {
    Remove-Item -LiteralPath $DestFull -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $DestFull | Out-Null

function Copy-FileToPackage {
    param([string]$Source, [string]$Target)
    $targetPath = Join-Path $DestFull $Target
    New-Item -ItemType Directory -Force -Path (Split-Path $targetPath -Parent) | Out-Null
    Copy-Item -LiteralPath (Join-Path $RootFull $Source) -Destination $targetPath -Force
}

function Copy-DirectoryToPackage {
    param([string]$Source, [string]$Target)
    $sourcePath = Join-Path $RootFull $Source
    $targetPath = Join-Path $DestFull $Target
    New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
    Copy-Item -Path (Join-Path $sourcePath "*") -Destination $targetPath -Recurse -Force
}

Copy-FileToPackage "README.md" "README_project.md"
Copy-FileToPackage "codebook.md" "codebook.md"
Copy-FileToPackage "preregistration.md" "preregistration.md"
Copy-FileToPackage "DEVIATIONS.md" "DEVIATIONS.md"
Copy-FileToPackage "requirements.txt" "requirements.txt"
Copy-FileToPackage "runner.py" "runner.py"
Copy-FileToPackage "run_formal.py" "run_formal.py"
Copy-FileToPackage "run_authentic_robustness.py" "run_authentic_robustness.py"
Copy-FileToPackage "corpus\corpus_manifest.csv" "corpus\corpus_manifest.csv"
Copy-FileToPackage "corpus\SHA256SUMS.txt" "corpus\SHA256SUMS.txt"
Copy-FileToPackage "config\models.yaml" "config\models.yaml"
Copy-DirectoryToPackage "tasks" "tasks"
Copy-DirectoryToPackage "prompts" "prompts"
Copy-DirectoryToPackage "harness" "harness"
Copy-DirectoryToPackage "analysis" "analysis"
Copy-DirectoryToPackage "figures" "figures"
Copy-DirectoryToPackage "teacher_phrasings" "teacher_phrasings"

New-Item -ItemType Directory -Force -Path (Join-Path $DestFull "runs\raw\formal\tables") | Out-Null
Copy-FileToPackage "runs\raw\formal\formal.jsonl" "runs\raw\formal\formal.jsonl"
if (Test-Path -LiteralPath (Join-Path $RootFull "runs\raw\formal\status.txt")) {
    Copy-FileToPackage "runs\raw\formal\status.txt" "runs\raw\formal\status.txt"
}
if (Test-Path -LiteralPath (Join-Path $RootFull "runs\raw\formal\formal_failures.jsonl")) {
    Copy-FileToPackage "runs\raw\formal\formal_failures.jsonl" "runs\raw\formal\formal_failures.jsonl"
}
Copy-Item -Path (Join-Path $RootFull "runs\raw\formal\tables\*") -Destination (Join-Path $DestFull "runs\raw\formal\tables") -Force

if (Test-Path -LiteralPath (Join-Path $RootFull "runs\raw\authentic_teacher\robustness.jsonl")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $DestFull "runs\raw\authentic_teacher\tables") | Out-Null
    Copy-FileToPackage "runs\raw\authentic_teacher\robustness.jsonl" "runs\raw\authentic_teacher\robustness.jsonl"
    if (Test-Path -LiteralPath (Join-Path $RootFull "runs\raw\authentic_teacher\status.txt")) {
        Copy-FileToPackage "runs\raw\authentic_teacher\status.txt" "runs\raw\authentic_teacher\status.txt"
    }
    if (Test-Path -LiteralPath (Join-Path $RootFull "runs\raw\authentic_teacher\robustness_failures.jsonl")) {
        Copy-FileToPackage "runs\raw\authentic_teacher\robustness_failures.jsonl" "runs\raw\authentic_teacher\robustness_failures.jsonl"
    }
    if (Test-Path -LiteralPath (Join-Path $RootFull "runs\raw\authentic_teacher\tables")) {
        Copy-Item -Path (Join-Path $RootFull "runs\raw\authentic_teacher\tables\*") -Destination (Join-Path $DestFull "runs\raw\authentic_teacher\tables") -Force
    }
}

Get-ChildItem -Path $DestFull -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $DestFull -Recurse -File -Include "*.pyc","*.aux","*.log","*.fdb_latexmk","*.fls","*.synctex.gz" | Remove-Item -Force

$releaseReadme = @"
# Paper A Anonymous Replication Package

This package supports the manuscript:

Can LLMs Teach Classical Literature Live? Benchmarking Quotation Fidelity and Textual Grounding

The package is anonymous and excludes API keys, `api.txt`, author names, affiliations, and local absolute paths.

## Main Reproduction Checks

```powershell
python harness\validate_tasks.py
python harness\run_validation.py
python analysis\formal_summary.py --expect-complete
python analysis\error_taxonomy_intervals.py
```

## Expected Formal Counts

- 2,160 unique formal records.
- 720 records per model.
- 540 records per condition.
- 120 records per task.
- 0 transport-failure records in the completed formal log.

## Authentic Teacher Robustness

The authentic-teacher robustness check has been executed: 180 generations (10 tasks, conditions C1 and C3, three models, three repetitions). The phrasings were independently authored by two consenting classroom teachers and are included in anonymized form in teacher_phrasings\authentic_teacher_phrasings.csv, with no teacher-identifying information. The run log and summary are in runs\raw\authentic_teacher\. This check is separate from the 2,160-generation confirmatory analysis; it did not reproduce the grounding advantage on its ten-task slice and is reported as a limitation, not as external validity. Regenerate its summary with: python analysis\robustness_summary.py
"@

Set-Content -LiteralPath (Join-Path $DestFull "README.md") -Value $releaseReadme -Encoding UTF8

Write-Host "Anonymous package built at $DestFull"
