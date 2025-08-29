import os
from graphviz import Digraph
from dataclasses import dataclass, field
from typing import List, Optional
from collections import defaultdict
from agents import Agent
import uuid
import re
from custom_runners  import CRunner
import textwrap

class AgentGraph:
    def __init__(self, name="Agent Interaction Graph"):
        self.graph = Digraph(comment=name)
        
        self.graph.attr(rankdir="TB")     # TB = Top to Bottom (use LR for Left to Right)
        self.graph.attr(nodesep="0.6")    # Horizontal spacing between nodes
        self.graph.attr(ranksep="1")    # Vertical spacing between levels
        self.graph.attr(ratio="compress") # Try: "auto", "compress", or "fill"
        self.graph.attr(dpi="150")        # Controls scale/resolution
        self.graph.attr(fontsize="10")    # Smaller font helps packing
        
        self._added_nodes = set()
        self._name_counts = defaultdict(int)
        self._agent_map = {}  # Stores label -> node_id for future connections

    def clean_string(self,text: str) -> str:
        # Replace newlines and tabs with a space
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        # Collapse multiple spaces into one
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing spaces
        text_wrapped = textwrap.fill(text, width=25)
        return text_wrapped

    def _generate_unique_id(self, label):
        # Convert to lowercase, replace spaces with underscores
        slug = re.sub(r'\W+', '_', label.lower()).strip('_')
        
        # Add short UUID (first 4–6 chars)
        short_uuid = uuid.uuid4().hex[:4]
        
        self._name_counts[label] += 1
        # return f"{label.lower().replace(' ', '_')}_{self._name_counts[label]}"
        
        return f"{slug}_{short_uuid}"

    def add_item(self, agent_obj, parent_id, color="lightblue", shape='box',style="filled", style_edge='solid'):
        if type(agent_obj) == CRunner:
            label = agent_obj.agent.name
            # node_id = self._generate_unique_id(label)
            node_id = agent_obj.agent_id

            self.graph.node(node_id, label, shape=shape, style="rounded,filled", fillcolor=color)

            
            
            self._added_nodes.add(node_id)
            self._agent_map[agent_obj.agent.name] = node_id

            # Link to parent if provided
            if parent_id:
                self.graph.edge(parent_id, node_id, style=style_edge)

            # Auto-add tools if any
            # for tool in agent_obj.agent.tools:
            #     tool_name = tool.name
            #     tool_id = self._generate_unique_id(tool_name)
            #     self.graph.node(tool_id, tool_name, shape="ellipse", style="filled", fillcolor="lightgreen")
            #     self.graph.edge(node_id, tool_id, style="dotted")

            return node_id

        elif type(agent_obj) == str:
            label = self.clean_string(agent_obj)

            node_id = self._generate_unique_id(label)
            
            self.graph.node(node_id, label, shape="box", style=style, fillcolor=color)
            self._added_nodes.add(node_id)
            self._agent_map[label] = node_id
            if parent_id:
                self.graph.edge(parent_id, node_id, style=style_edge)
                
            return node_id
            
            
            
    def add_edge(self, parent_id, node_id,  style_edge='solid'):
        self.graph.edge(parent_id, node_id, style=style_edge)


    def add_edge_by_name(self, from_agent: str, to_agent: str, label=None, style="solid"):
        source = self._agent_map.get(from_agent)
        target = self._agent_map.get(to_agent)
        if source and target:
            self.graph.edge(source, target, label=label, style=style)

    def add_entry_exit(self, label, color="lightblue"):
        node_id = self._generate_unique_id(label)
        self.graph.node(node_id, label, shape="ellipse", style="filled", fillcolor=color)
        self._added_nodes.add(node_id)
        self._agent_map[label] = node_id
        return node_id

    def render(self, filename="agent_graph_test", format="png", directory=".", view=False):
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, filename)
        self.graph.render(filepath, format=format, cleanup=True)
        if view:
            self.graph.view(filepath)