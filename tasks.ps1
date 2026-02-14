param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("test", "baseline", "optimize", "run", "sweep", "feasibility", "executive")]
    [string]$Task,
    [string]$Config = "configs/trial-001.yaml",
    [string]$ModelPoint = "male_age30_term35",
    [double]$Start = 1.0,
    [double]$End = 1.05,
    [double]$Step = 0.01,
    [double]$IrrThreshold = 0.02
)

switch ($Task) {
    "test" {
        python -m pytest -q
        break
    }
    "baseline" {
        python -m pricing.cli run $Config
        python -m pricing.cli report-feasibility $Config --r-start $Start --r-end $End --r-step $Step --irr-threshold $IrrThreshold
        break
    }
    "optimize" {
        python -m pricing.cli optimize $Config
        break
    }
    "run" {
        python -m pricing.cli run $Config
        break
    }
    "sweep" {
        python -m pricing.cli sweep-ptm $Config --model-point $ModelPoint --start $Start --end $End --step $Step
        break
    }
    "feasibility" {
        python -m pricing.cli report-feasibility $Config --r-start $Start --r-end $End --r-step $Step --irr-threshold $IrrThreshold
        break
    }
    "executive" {
        python -m pricing.cli report-executive-pptx $Config --r-start $Start --r-end $End --r-step $Step --irr-threshold $IrrThreshold
        break
    }
}
