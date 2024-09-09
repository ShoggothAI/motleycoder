## motleycoder: a code editor for AI agents

This is a collection of tools and utilities that help agents write code.

MotleyCoder uses a combination of static code analysis and retrieval techniques for building a map of the codebase and navigating it.

MotleyCoder consists of the following main elements:
- `RepoMap`: provides the agent with an initial overview of the parts of the codebase relevant to the current task. This uses tree-sitter to build formal syntax trees of the code, and then builds a graph of relationships between entities in the code. 
- `InspectEntityTool`: a tool given to the agent so it can inspect and navigate the codebase, read the code of specific entities or files, and list directories. This uses the graph built by RepoMap to enrich the information about each entity with a summary of the entities it references.
- `FileEditTool`: a tool that allows editing code in a way an LLM can comprehend. This comes with a built-in linter, so only syntactically valid edits are accepted, else the tool returns a description of the linting errors so the LLM can try again.

Please check out the [demo notebook](https://github.com/ShoggothAI/motleycoder/blob/main/motleycoder_demo.ipynb) to see how it all works.

MotleyCoder was originally designed for use with our [motleycrew](https://github.com/ShoggothAI/motleycrew) library, but its flexible nature allows using it in other contexts.

Credits to [aider](https://github.com/paul-gauthier/aider) for the original idea of the RepoMap and of using tree-sitter for code parsing.

## Installation

```
pip install motleycoder
```
