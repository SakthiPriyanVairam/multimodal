import os
from typing import TYPE_CHECKING, List, Optional, Union

if TYPE_CHECKING:
    from llama_index.core.bridge.langchain import Embeddings as LCEmbeddings
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.callbacks import CallbackManager
from llama_index.core.embeddings.mock_embed_model import MockEmbedding
from llama_index.core.utils import get_cache_dir

EmbedType = Union[BaseEmbedding, "LCEmbeddings", str]

def save_embedding(embedding: List[float], file_path: str) -> None:
    """Save embedding to file."""
    with open(file_path, "w") as f:
        f.write(",".join([str(x) for x in embedding]))

def load_embedding(file_path: str) -> List[float]:
    """Load embedding from file. Will only return first embedding in file."""
    with open(file_path) as f:
        for line in f:
            embedding = [float(x) for x in line.strip().split(",")]
            break
        return embedding

def get_azure_openai_embedding(text: str, api_key: str, endpoint: str, model_name: str, api_version: str) -> List[float]:
    """Fetch embeddings from Azure OpenAI."""
    from llama_index.legacy.multi_modal_llms.azure_openai import AzureOpenAIMultiModal

    azure_openai_multi_modal = AzureOpenAIMultiModal(
        model=model_name,
        engine="your_deployment_name",  # Replace with your deployment name
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version
    )

    response = azure_openai_multi_modal.embed(text)
    return response['data'][0]['embedding']

def resolve_embed_model(
    embed_model: Optional[EmbedType] = None,
    callback_manager: Optional[CallbackManager] = None,
) -> BaseEmbedding:
    """Resolve embed model."""
    from llama_index.core.settings import Settings

    try:
        from llama_index.core.bridge.langchain import Embeddings as LCEmbeddings
    except ImportError:
        LCEmbeddings = None  # type: ignore

    if embed_model == "default":
        if os.getenv("IS_TESTING"):
            embed_model = MockEmbedding(embed_dim=8)
            embed_model.callback_manager = callback_manager or Settings.callback_manager
            return embed_model

        try:
            from llama_index.embeddings.openai import (
                OpenAIEmbedding,
            )  # pants: no-infer-dep

            from llama_index.embeddings.openai.utils import (
                validate_openai_api_key,
            )  # pants: no-infer-dep

            embed_model = OpenAIEmbedding()
            validate_openai_api_key(embed_model.api_key)
        except ImportError:
            raise ImportError(
                "`llama-index-embeddings-openai` package not found, "
                "please run `pip install llama-index-embeddings-openai`"
            )
        except ValueError as e:
            raise ValueError(
                "\n******\n"
                "Could not load OpenAI embedding model. "
                "If you intended to use OpenAI, please check your OPENAI_API_KEY.\n"
                "Original error:\n"
                f"{e!s}"
                "\nConsider using embed_model='local'.\n"
                "Visit our documentation for more embedding options: "
                "https://docs.llamaindex.ai/en/stable/module_guides/models/"
                "embeddings.html#modules"
                "\n******"
            )
    # for image multi-modal embeddings
    elif isinstance(embed_model, str) and embed_model.startswith("clip"):
        try:
            from llama_index.embeddings.clip import ClipEmbedding  # pants: no-infer-dep

            clip_model_name = (
                embed_model.split(":")[1] if ":" in embed_model else "ViT-B/32"
            )
            embed_model = ClipEmbedding(model_name=clip_model_name)
        except ImportError as e:
            raise ImportError(
                "`llama-index-embeddings-clip` package not found, "
                "please run `pip install llama-index-embeddings-clip` and `pip install git+https://github.com/openai/CLIP.git`"
            )

    if isinstance(embed_model, str):
        try:
            from llama_index.embeddings.huggingface import (
                HuggingFaceEmbedding,
            )  # pants: no-infer-dep

            splits = embed_model.split(":", 1)
            is_local = splits[0]
            model_name = splits[1] if len(splits) > 1 else None
            if is_local != "local":
                raise ValueError(
                    "embed_model must start with str 'local' or of type BaseEmbedding"
                )

            cache_folder = os.path.join(get_cache_dir(), "models")
            os.makedirs(cache_folder, exist_ok=True)

            embed_model = HuggingFaceEmbedding(
                model_name=model_name, cache_folder=cache_folder
            )
        except ImportError:
            raise ImportError(
                "`llama-index-embeddings-huggingface` package not found, "
                "please run `pip install llama-index-embeddings-huggingface`"
            )

    if LCEmbeddings is not None and isinstance(embed_model, LCEmbeddings):
        try:
            from llama_index.embeddings.langchain import (
                LangchainEmbedding,
            )  # pants: no-infer-dep

            embed_model = LangchainEmbedding(embed_model)
        except ImportError as e:
            raise ImportError(
                "`llama-index-embeddings-langchain` package not found, "
                "please run `pip install llama-index-embeddings-langchain`"
            )

    if isinstance(embed_model, str) and embed_model.startswith("azure-openai"):
        splits = embed_model.split(":")
        if len(splits) != 4:
            raise ValueError(
                "For Azure OpenAI, embed_model should be of the form 'azure-openai:<endpoint>:<model_name>:<api_version>'"
            )
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "AZURE_OPENAI_API_KEY environment variable is not set."
            )
        endpoint, model_name, api_version = splits[1], splits[2], splits[3]
        embed_model = get_azure_openai_embedding(embed_model, api_key, endpoint, model_name, api_version)

    if embed_model is None:
        print("Embeddings have been explicitly disabled. Using MockEmbedding.")
        embed_model = MockEmbedding(embed_dim=1)

    embed_model.callback_manager = callback_manager or Settings.callback_manager

    return embed_model
