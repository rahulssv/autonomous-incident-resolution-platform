import os
import ssl

import httpx
from llama_index.core.llms import  ChatMessage, LLMMetadata
from llama_index.llms.openai import OpenAI
# from llama_index.agent import ReActAgent

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

llm = OpenAI(
  model=model,
  api_key=gateway_api_key,
  api_base=gateway_base_url, # api_base represents the endpoint the Llama-Index object will make a call to when invoked
  temperature=0.1,
  max_tokens=4096,
  http_client=httpx_client,
)
# Adjust the below parameters as per the model you've chosen
llm.__class__.metadata = LLMMetadata(
  context_window=4096, 
  num_output=4096,
  is_chat_model=True,
  is_function_calling_model=False, 
  model_name=model,
)
print(llm.chat([ChatMessage(role="user",content="write a thousand word essay on the sky")]).message.content)
# agent = ReActAgent.from_tools(tools=[],llm=llm) 