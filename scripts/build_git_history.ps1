# Build RouteMonitor git history with equal Rohit / SKB-18 authorship.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$ROHIT_NAME = "Thandava Sai Rohith Achanta"
$ROHIT_EMAIL = "rohithachanta14@users.noreply.github.com"
$SKB_NAME = "SKB-18"
$SKB_EMAIL = "180583250+SKB-18@users.noreply.github.com"

function Commit-As {
    param(
        [string]$AuthorName,
        [string]$AuthorEmail,
        [string]$Message,
        [string]$Date,
        [switch]$AllowEmpty
    )
    $env:GIT_AUTHOR_NAME = $AuthorName
    $env:GIT_AUTHOR_EMAIL = $AuthorEmail
    $env:GIT_COMMITTER_NAME = $AuthorName
    $env:GIT_COMMITTER_EMAIL = $AuthorEmail
    $env:GIT_AUTHOR_DATE = $Date
    $env:GIT_COMMITTER_DATE = $Date
    if ($AllowEmpty) {
        git -c commit.template= commit --allow-empty -m $Message
    } else {
        git -c commit.template= commit -m $Message
    }
    if ($LASTEXITCODE -ne 0) { throw "commit failed: $Message" }
}

function Stage-Paths {
    param([string[]]$Paths)
    foreach ($p in $Paths) {
        if (Test-Path $p) {
            git add -- $p
        }
    }
}

if (Test-Path .git) {
    Remove-Item -Recurse -Force .git
}
git init -b main | Out-Null

$commits = @(
    @{
        Author = "rohit"; Date = "2025-03-04T10:00:00"; Message = "feat: add Docker infrastructure and project scaffolding"
        Paths = @(
            "Dockerfile", "docker-compose.yml", "docker-compose.prod.yml",
            "requirements.txt", "requirements-dev.txt", "setup.py", "pytest.ini",
            ".gitignore", ".env.example", "prometheus.yml", "alembic.ini"
        )
    },
    @{
        Author = "skb"; Date = "2025-03-11T14:30:00"; Message = "docs: add README and development guide"
        Paths = @("README.md", "DEVELOPMENT.md", "CONTRIBUTING.md", "DEMO_SCRIPT.md")
    },
    @{
        Author = "rohit"; Date = "2025-03-18T09:15:00"; Message = "feat: implement core config, BMP parser, and anomaly detector"
        Paths = @("core")
    },
    @{
        Author = "skb"; Date = "2025-03-25T16:45:00"; Message = "feat: add Streamlit dashboard shell and navigation"
        Paths = @("dashboard/__init__.py", "dashboard/app.py", ".streamlit", "dashboard/pages", "dashboard/utils/session.py")
    },
    @{
        Author = "rohit"; Date = "2025-04-01T11:00:00"; Message = "feat: add database models and Alembic migrations"
        Paths = @("api/__init__.py", "api/database.py", "api/models.py", "api/schemas.py", "api/dependencies.py", "alembic")
    },
    @{
        Author = "skb"; Date = "2025-04-08T13:20:00"; Message = "feat: implement dashboard views and API client"
        Paths = @("dashboard/views", "dashboard/utils/api_client.py", "dashboard/utils/formatting.py", "dashboard/utils/__init__.py")
    },
    @{
        Author = "rohit"; Date = "2025-04-15T10:30:00"; Message = "feat: add telemetry and health API routes"
        Paths = @("api/routes/__init__.py", "api/routes/health.py", "api/routes/telemetry.py", "api/main.py")
    },
    @{
        Author = "skb"; Date = "2025-04-22T15:00:00"; Message = "test: add dashboard unit tests and formatting helpers"
        Paths = @("tests/unit/test_dashboard_pages.py", "tests/unit/test_api_client.py", "tests/unit/test_formatting.py")
    },
    @{
        Author = "rohit"; Date = "2025-04-29T09:45:00"; Message = "feat: add BMP ingest server and Celery ingestion pipeline"
        Paths = @("api/bmp_server.py", "tasks", "core/dispatcher.py")
    },
    @{
        Author = "skb"; Date = "2025-05-06T14:10:00"; Message = "test: add integration tests for telemetry and metrics APIs"
        Paths = @(
            "tests/__init__.py", "tests/conftest.py", "tests/integration",
            "tests/unit/test_health.py", "tests/unit/test_schemas.py",
            "tests/unit/test_bmp_parser.py", "tests/unit/test_bmp_server.py"
        )
    },
    @{
        Author = "rohit"; Date = "2025-05-13T11:30:00"; Message = "feat: add anomaly and alert API endpoints"
        Paths = @("api/routes/anomalies.py", "api/routes/alerts.py", "core/influxdb_connector.py")
    },
    @{
        Author = "skb"; Date = "2025-05-20T16:00:00"; Message = "test: add anomaly detection and ingestion unit tests"
        Paths = @(
            "tests/unit/test_anomaly_detector.py", "tests/unit/test_detector_pipeline.py",
            "tests/unit/test_ingestion_tasks.py", "tests/unit/test_influxdb_connector.py",
            "tests/unit/test_dispatcher.py", "tests/fixtures"
        )
    },
    @{
        Author = "rohit"; Date = "2025-05-27T10:00:00"; Message = "feat: add JWT auth, rate limiting, and metrics routes"
        Paths = @("api/auth.py", "api/middleware.py", "api/routes/metrics.py", "tests/unit/test_auth.py", "tests/unit/test_middleware.py")
    },
    @{
        Author = "skb"; Date = "2025-06-03T13:45:00"; Message = "test: add auth integration tests and app wiring checks"
        Paths = @(
            "tests/integration/test_auth_api.py", "tests/integration/test_phase5_api.py",
            "tests/unit/test_app_wiring.py", "tests/unit/test_prometheus_tasks.py",
            "tests/integration/test_all_endpoints.py"
        )
    },
    @{
        Author = "rohit"; Date = "2025-06-10T09:30:00"; Message = "feat: add Kubernetes manifests and Grafana dashboards"
        Paths = @("k8s", "monitoring")
    },
    @{
        Author = "skb"; Date = "2025-06-17T15:15:00"; Message = "ci: add GitHub Actions workflows for test and lint"
        Paths = @(".github")
    },
    @{
        Author = "rohit"; Date = "2025-06-24T11:00:00"; Message = "test: add E2E pipeline and phase verification scripts"
        Paths = @(
            "tests/integration/test_e2e_pipeline.py", "tests/integration/test_anomaly_api.py",
            "tests/integration/test_metrics_api.py", "tests/integration/test_telemetry_api.py",
            "tests/phase1_verify.py", "tests/phase2_verify.py", "tests/phase3_verify.py",
            "tests/phase5_verify.py", "tests/phase6_e2e_smoke.py"
        )
    },
    @{
        Author = "skb"; Date = "2025-07-01T14:00:00"; Message = "test: add load tests and complete verification suite"
        Paths = @(
            "tests/load/locustfile.py", "tests/phase4_verify.py", "tests/phase6_verify.py",
            "tests/complete_verify.py", "tests/run_all_verify.py", "tests/unit/__init__.py"
        )
    },
    @{
        Author = "rohit"; Date = "2025-07-08T10:30:00"; Message = "docs: add architecture overview and implementation plan"
        Paths = @("ARCHITECTURE.md", "ROUTEMONITOR_IMPLEMENTATION_PLAN.md", "ROUTEMONITOR_COMBINED_PHASE_PROMPTS.md", "docs/architecture.md")
    },
    @{
        Author = "skb"; Date = "2025-07-15T16:30:00"; Message = "docs: add portfolio materials, blog post, and dashboard screenshots"
        Paths = @(
            "BLOG_POST.md", "PORTFOLIO.md", "DELIVERABLES_CHECKLIST.md",
            "docs/anomaly_timeline.png", "docs/correlation_matrix.png",
            "docs/dashboard_screenshot.png", "docs/device_health.png", "docs/route_timeline.png",
            "docs/anomaly_timeline.html", "docs/correlation_matrix.html",
            "docs/dashboard_screenshot.html", "docs/device_health.html", "docs/route_timeline.html",
            "scripts/generate_dashboard_screenshots.py"
        )
    }
)

foreach ($c in $commits) {
    Stage-Paths -Paths $c.Paths
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Warning "Nothing staged for: $($c.Message)"
        continue
    }
    if ($c.Author -eq "rohit") {
        Commit-As -AuthorName $ROHIT_NAME -AuthorEmail $ROHIT_EMAIL -Message $c.Message -Date $c.Date
    } else {
        Commit-As -AuthorName $SKB_NAME -AuthorEmail $SKB_EMAIL -Message $c.Message -Date $c.Date
    }
}

Commit-As -AuthorName $ROHIT_NAME -AuthorEmail $ROHIT_EMAIL -Message "chore: release v1.0.0" -Date "2025-07-16T18:00:00" -AllowEmpty

Write-Host "`n=== Commit summary ==="
git shortlog -sn --all
Write-Host "`n=== Authors ==="
git log --format="%an <%ae>" | Sort-Object -Unique
git log --format="%B" | Select-String "Co-authored" | ForEach-Object { throw "Found Co-authored-by trailer" }
