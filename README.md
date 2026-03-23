adobe-de-assessment

src/
  search_keyword_performance.py   core logic — HitDataParser, ReportWriter
  lambda_handler.py               AWS Lambda entry point (EventBridge trigger)

tests/
  test_analyzer.py                unit + integration tests (pytest)

data/
  data.sql                        sample hit-level TSV input

docs/
  SearchKeyword_BusinessCase_Presentation.pptx business problem + architecture overview

template.yaml                     SAM template — Lambda, S3, EventBridge, IAM
.github/
  workflows/
    deploy.yml                      CI/CD — runs tests, then sam deploy on push to develop

