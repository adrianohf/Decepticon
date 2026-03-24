#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import { App } from "./app.js";

const instance = render(<App />, {
  patchConsole: true,
  exitOnCtrlC: false,
});

await instance.waitUntilExit();
