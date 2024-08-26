## motleycoder: a code editor for AI agents

This is a collection of tools and utilities that help agents write code.

MotleyCoder uses a combination of static code analysis and retrieval techniques for building a map of the codebase and navigating it.

MotleyCoder consists of the following main elements:
- `RepoMap`: provides the agent with an initial overview of the parts of the codebase relevant to the current task.
- `InspectEntityTool`: a tool given to the agent so it can inspect and navigate the codebase, read the code of specific entities or files, and list directories.
- `FileEditTool`: a tool that allows editing code in a way an LLM can comprehend.

Please check out the [demo notebook](https://github.com/ShoggothAI/motleycoder/blob/main/motleycoder_demo.ipynb) to see how it all works.

MotleyCoder was originally designed for use with our [motleycrew](https://github.com/ShoggothAI/motleycrew) library, but its flexible nature allows using it in other contexts.

Credits to [aider](https://github.com/paul-gauthier/aider) for the original idea and code of the RepoMap.
