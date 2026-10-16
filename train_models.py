"""Train the reranker, the claim verifier and the adverse event extractor."""
from vigilix.extraction.ade import train_and_evaluate
from vigilix.rag.train_reranker import train as train_reranker
from vigilix.rag.verifier import train_verifier

if __name__ == "__main__":
    print("reranker"); train_reranker()
    print("verifier"); train_verifier()
    print("adverse event extractor"); train_and_evaluate()
