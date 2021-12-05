from google.cloud import storage


def upload_blob(bucket_name, data, destination_blob_name, public=True, client=storage.Client()):
    """Uploads a file to the bucket."""
    # The ID of your GCS bucket
    # bucket_name = "your-bucket-name"
    # The path to your file to upload
    # source_file_name = "local/path/to/file"
    # The ID of your GCS object
    # destination_blob_name = "storage-object-name"

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_string(data)
    print("File of len {} uploaded to {}.".format(len(data), destination_blob_name))

    if public:
        blob.make_public()

    return blob.public_url

