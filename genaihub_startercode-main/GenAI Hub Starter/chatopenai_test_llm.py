import os
import ssl

import httpx
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage

from dotenv import load_dotenv

load_dotenv()


model = os.environ.get("MODEL")
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


messages = [
  HumanMessage(content="What is agentic ai?"),
]
llm = ChatOpenAI(
  model=model,
  temperature=0.1,
  max_tokens=4096,
  base_url=gateway_base_url,
  api_key=gateway_api_key,
  http_client=httpx_client,
)
print(llm.invoke(messages).content)