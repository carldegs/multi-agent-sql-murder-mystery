# 🕵️‍♀️ Multi-Agent SQL Murder Mystery Solver

A collaborative AI-powered application designed to solve the [SQL Murder Mystery game](https://mystery.knightlab.com/) using a graph-based, multi-agent system built with [Pydantic AI](https://ai.pydantic.dev/multi-agent-applications/).

## 🧠 Overview

The project creates a graph-based control flow multi-agent app that can generate SQL queries and coordinate the next steps to be done to solve the SQL Murder Mystery game.

## 🔧 Setup

- Run `uv sync` to sync the environment and install the dependencies
- Get `sql-murder-mystery.db` from the [game's original repository](https://github.com/NUKnightLab/sql-mysteries/blob/master/sql-murder-mystery.db) and place it in the root folder.
- The project uses [Pydantic Logfire](https://pydantic.dev/logfire) for tracing. To use it:
  - setup an account
  - run `uv run logfire auth` to authenticate your local environment
  - configure it by running `uv run logfire projects new`
- We are using the `openai:gpt-4o` model. Follow the instructions [here](https://ai.pydantic.dev/models/) on installing and configuring the models
- To run the app, `uv run graph.py`

## ⚙️ How it Works

TODO