param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("test", "baseline", "optimize", "run", "sweep")]
    [string]$Task,
    [string]$Config = "configs/trial-001.yaml",
    [string]$ModelPoint = "male_age30_term35",
    [double]$Start = 1.0,
    [double]$End = 1.05,
    [double]$Step = 0.01
)

switch ($Task) {
    "test" {
        python -m pytest -q
        break
    }
    "baseline" {
        python -m pricing.cli report-feasibility $Config
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
}
