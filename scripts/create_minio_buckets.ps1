Param(
    [string]$MinioRootUser = $(if ($Env:MINIO_ROOT_USER) { $Env:MINIO_ROOT_USER } else { "minioadmin" }),
    [string]$MinioRootPassword = $(if ($Env:MINIO_ROOT_PASSWORD) { $Env:MINIO_ROOT_PASSWORD } else { "minioadmin" }),
    [string]$MinioBucket = $(if ($Env:MINIO_BUCKET) { $Env:MINIO_BUCKET } else { "jarvis" })
)

$mcHostLocal = "http://$MinioRootUser`:$MinioRootPassword@minio:9000"
docker compose run --rm -e MC_HOST_local=$mcHostLocal minio-mc mb -p "local/$MinioBucket"
docker compose run --rm -e MC_HOST_local=$mcHostLocal minio-mc ls local
