#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import { App } from "./app.js";

const initialMessage = process.env.DECEPTICON_INITIAL_MESSAGE || undefined;

const instance = render(<App initialMessage={initialMessage} />, {
  patchConsole: true,
  exitOnCtrlC: false,
});

await instance.waitUntilExit();
