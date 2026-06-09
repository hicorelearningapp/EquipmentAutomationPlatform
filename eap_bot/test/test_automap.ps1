$json = @'
{
  "project_id": 1,
  "family": "FactoryWorks",
  "template": "STANDARD_EVENT_MODEL.json"
}
'@

curl.exe -X POST "http://151.185.41.194:8012/AutoMap" -H "accept: application/json" -H "Content-Type: application/json" -d $json
