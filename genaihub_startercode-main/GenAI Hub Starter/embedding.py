# Embedding model
import os
import ssl

import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


model =  os.environ.get("MODEL")
gateway_base_url = os.environ.get("GATEWAY_BASE_URL")
gateway_api_key = os.environ.get("GATEWAY_API_KEY")



ca_bundle = os.getenv("SSL_CERT_FILE", os.getenv("REQUESTS_CA_BUNDLE"))
ssl_context = ssl.create_default_context(cafile=ca_bundle)
# Zscaler cert doesn't mark basic constraints as critical
# Python versions greater than 3.13 require that by default, this is workaround for trusting Zscaler's cert
ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

httpx_client = httpx.Client(
    verify=ssl_context
)

openai_client = OpenAI(
    api_key=gateway_api_key,
    base_url=gateway_base_url,
    http_client=httpx_client,
)
response = openai_client.embeddings.create(
    input="hi",
    model=model
)

print(response.dict()['data'][0]['embedding'])