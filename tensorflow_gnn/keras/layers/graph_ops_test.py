# Copyright 2021 The TensorFlow GNN Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for graph_ops Keras layers."""
from unittest import mock

from absl.testing import parameterized
import tensorflow as tf

from tensorflow_gnn.graph import adjacency as adj
from tensorflow_gnn.graph import graph_constants as const
from tensorflow_gnn.graph import graph_tensor as gt
from tensorflow_gnn.keras.layers import graph_ops


class ReadoutTest(tf.test.TestCase, parameterized.TestCase):

  def testFeatureName(self):
    red_values = tf.constant([[11., 12.]])
    blue_values = tf.constant([[21., 22.]])
    default_values = tf.constant([[31., 32.]])
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(
            features={"red": red_values, "blue": blue_values,
                      const.HIDDEN_STATE: default_values}))

    readout = graph_ops.Readout(from_context=True, feature_name="red")
    self.assertEqual("red", readout.feature_name)
    self.assertAllEqual(red_values, readout(graph))

    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      readout(graph, feature_name="blue")

    self.assertAllEqual(default_values,
                        graph_ops.Readout(from_context=True)(graph))

  @parameterized.parameters("context", "nodes", "edges")
  def testFeatureLocation(self, origin):
    values = dict(
        context=tf.constant([[1.0, 1.5]]),
        nodes=tf.constant([[11.0 + k, 11.5 + k] for k in range(3)]),
        edges=tf.constant([[21.0 + k, 21.5 + k] for k in range(4)]))
    graph = self._make_test_graph_134(values)
    value = values[origin]
    location_kwarg = dict(context=dict(from_context=True),
                          nodes=dict(node_set_name="nodes"),
                          edges=dict(edge_set_name="edges"))[origin]

    readout = graph_ops.Readout(feature_name="value", **location_kwarg)
    self.assertEqual(location_kwarg, readout.location)
    self.assertAllEqual(value, readout(graph))
    self.assertAllEqual(value, readout(graph, feature_name="value"))
    self.assertAllEqual(value, readout(graph, **location_kwarg))
    self.assertAllEqual(value, readout(graph, feature_name="value",
                                       **location_kwarg))

    readout = graph_ops.Readout(**location_kwarg)
    self.assertEqual(location_kwarg, readout.location)
    self.assertAllEqual(value, readout(graph, feature_name="value"))

    readout = graph_ops.Readout(feature_name="value")
    self.assertEqual({}, readout.location)
    self.assertAllEqual(value, readout(graph, **location_kwarg))

    readout = graph_ops.Readout()
    self.assertEqual({}, readout.location)
    self.assertAllEqual(value,
                        readout(graph, feature_name="value", **location_kwarg))

  @parameterized.named_parameters(
      ("Nodes", dict(node_set_name="nodes")),
      ("Edges", dict(edge_set_name="edges")),
      ("Context", dict(from_context=True)))
  def testConflictingFeatureLocation(self, location_kwarg):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      readout = graph_ops.Readout(node_set_name="wronk", feature_name="value")
      _ = readout(graph, feature_name="value", **location_kwarg)

  @parameterized.named_parameters(
      ("ContextAndNodes", dict(from_context=True, node_set_name="nodes")),
      ("ContextAndEdges", dict(from_context=True, edge_set_name="edges")),
      ("NodesAndEdges", dict(node_set_name="nodes", edge_set_name="edges")),
      ("AllThree", dict(from_context=True, node_set_name="nodes",
                        edge_set_name="edges")))
  def testTooManyFeatureLocations(self, location_kwargs):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, "at most one of"):
      graph_ops.Readout(**location_kwargs)
    with self.assertRaisesRegex(ValueError, "at most one of"):
      graph_ops.Readout()(graph, **location_kwargs)

  def testNoFeatureLocation(self):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, "requires one of"):
      graph_ops.Readout(feature_name="value")(graph)

  @parameterized.parameters("context", "nodes", "edges")
  def testFromConfig(self, location):
    values = dict(
        context=tf.constant([[1.0, 1.5]]),
        nodes=tf.constant([[11.0 + v, 11.5 + v] for v in range(3)]),
        edges=tf.constant([[21.0 + v, 21.5 + v] for v in range(4)]))
    graph = self._make_test_graph_134(values)
    value = values[location]
    location_kwarg = dict(context=dict(from_context=True),
                          nodes=dict(node_set_name="nodes"),
                          edges=dict(edge_set_name="edges"))[location]
    kwargs = dict(location_kwarg, feature_name="value", name="test_readout")
    config = graph_ops.Readout(**kwargs).get_config()
    self.assertDictContainsSubset(kwargs, config)

    readout = graph_ops.Readout.from_config(config)
    self.assertEqual("value", readout.feature_name)
    self.assertEqual(location_kwarg, readout.location)
    self.assertAllEqual(value, readout(graph))

  @parameterized.parameters("context", "nodes", "edges")
  def testTFLite(self, location):
    values = dict(
        context=tf.constant([[1.0, 1.5]]),
        nodes=tf.constant([[11.0 + v, 11.5 + v] for v in range(3)]),
        edges=tf.constant([[21.0 + v, 21.5 + v] for v in range(4)]))
    test_graph_134_dict = {
        "nodes_value": values["nodes"],
        "edges_value": values["edges"],
        "context_value": values["context"],
        "source": tf.constant([0, 1, 1, 2]),
        "target": tf.constant([1, 0, 2, 1]),
    }
    inputs = {
        "nodes_value": tf.keras.Input([2], None, "nodes_value", tf.float32),
        "edges_value": tf.keras.Input([2], None, "edges_value", tf.float32),
        "context_value": tf.keras.Input([2], None, "context_value", tf.float32),
        "source": tf.keras.Input([], None, "source", tf.int32),
        "target": tf.keras.Input([], None, "target", tf.int32),
    }
    location_kwarg = dict(context=dict(from_context=True),
                          nodes=dict(node_set_name="nodes"),
                          edges=dict(edge_set_name="edges"))[location]
    kwargs = dict(location_kwarg, feature_name="value", name="test_readout")
    graph_in = _MakeGraphTensor()(inputs)
    readout = graph_ops.Readout(**kwargs)
    outputs = readout(graph_in)
    model = tf.keras.Model(inputs, outputs)
    expected = model(test_graph_134_dict)

    # TODO(b/276291104): Remove when TF 2.11+ is required by all of TFGNN
    if tf.__version__.startswith("2.9.") or tf.__version__.startswith("2.10."):
      self.skipTest("GNN models are unsupported in TFLite until TF 2.11 but "
                    f"got TF {tf.__version__}")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    model_content = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=model_content)
    signature_runner = interpreter.get_signature_runner("serving_default")
    obtained = signature_runner(**test_graph_134_dict)["test_readout"]
    self.assertAllEqual(expected, obtained)

  def _make_test_graph_134(self, values):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": values["context"]}),
        node_sets={"nodes": gt.NodeSet.from_fields(
            sizes=tf.constant([3]), features={"value": values["nodes"]})},
        edge_sets={"edges": gt.EdgeSet.from_fields(
            sizes=tf.constant([4]),
            features={"value": values["edges"]},
            adjacency=adj.Adjacency.from_indices(   # 0 <-> 1 <-> 2.
                ("nodes", tf.constant([0, 1, 1, 2])),
                ("nodes", tf.constant([1, 0, 2, 1]))))})
    return graph


class ReadoutFirstNodeTest(tf.test.TestCase, parameterized.TestCase):

  @parameterized.named_parameters(
      ("Dense", "dense", [[11.], [13.]]),
      ("Ragged", "ragged", tf.ragged.constant([[110., 111.], [130.]])))
  def testFeatureName(self, feature_name, expected):

    graph = self._make_test_graph_22()

    readout = graph_ops.ReadoutFirstNode(node_set_name="nodes",
                                         feature_name=feature_name)
    self.assertEqual(feature_name, readout.feature_name)
    self.assertAllEqual(expected, readout(graph))

    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      readout(graph, feature_name="other")

  def testFeatureNameDefault(self):
    graph = self._make_test_graph_22()
    self.assertAllEqual(
        [[1.], [3.]],
        graph_ops.ReadoutFirstNode(node_set_name="nodes")(graph))

  def testFeatureLocation(self):
    graph = self._make_test_graph_22()
    value = [[1.], [3.]]
    readout = graph_ops.ReadoutFirstNode(node_set_name="nodes")
    self.assertEqual(dict(node_set_name="nodes"), readout.location)
    self.assertAllEqual(value, readout(graph))
    self.assertAllEqual(value, readout(graph, node_set_name="nodes"))

    readout = graph_ops.ReadoutFirstNode()
    self.assertEqual({}, readout.location)
    self.assertAllEqual(value, readout(graph, node_set_name="nodes"))

  def testBadFeatureLocation(self):
    graph = self._make_test_graph_22()
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      readout = graph_ops.ReadoutFirstNode(node_set_name="wronk")
      _ = readout(graph, node_set_name="nodes")
    with self.assertRaisesRegex(ValueError, "requires node_set_name"):
      graph_ops.ReadoutFirstNode()(graph)

  def testFromConfig(self):
    graph = self._make_test_graph_22()
    value = [[11.], [13.]]
    kwargs = dict(node_set_name="nodes", feature_name="dense",
                  name="test_readout_first")
    config = graph_ops.ReadoutFirstNode(**kwargs).get_config()
    self.assertDictContainsSubset(kwargs, config)

    readout = graph_ops.ReadoutFirstNode.from_config(config)
    self.assertEqual("dense", readout.feature_name)
    self.assertEqual(dict(node_set_name="nodes"), readout.location)
    self.assertAllEqual(value, readout(graph))

  def testTFLite(self):
    test_graph_22_dict = {
        "node_sizes": tf.constant([2, 2]),
        "features_dense": tf.constant([[11.0], [12.0], [13.0], [14.0]]),
        "features": tf.constant([[1.0], [2.0], [3.0], [4.0]]),
    }
    inputs = {
        "node_sizes": tf.keras.Input([], None, "node_sizes", tf.int32),
        "features_dense": tf.keras.Input(
            [1], None, "features_dense", tf.float32
        ),
        "features": tf.keras.Input([1], None, "features", tf.float32),
    }
    kwargs = dict(node_set_name="nodes", feature_name="dense",
                  name="test_readout_first")
    graph_in = _MakeGraphTensorNodesOnly()(inputs)
    readout = graph_ops.ReadoutFirstNode(**kwargs)
    outputs = readout(graph_in)
    model = tf.keras.Model(inputs, outputs)
    expected = model(test_graph_22_dict)

    # TODO(b/276291104): Remove when TF 2.11+ is required by all of TFGNN
    if tf.__version__.startswith("2.9.") or tf.__version__.startswith("2.10."):
      self.skipTest("GNN models are unsupported in TFLite until TF 2.11 but "
                    f"got TF {tf.__version__}")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    model_content = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=model_content)
    signature_runner = interpreter.get_signature_runner("serving_default")
    obtained = signature_runner(**test_graph_22_dict)["test_readout_first"]
    self.assertAllEqual(expected, obtained)

  def _make_test_graph_22(self):
    graph = gt.GraphTensor.from_pieces(
        node_sets={"nodes": gt.NodeSet.from_fields(
            sizes=tf.constant([2, 2]),
            features={
                "dense": tf.constant([[11.], [12.], [13.], [14.]]),
                "ragged": tf.ragged.constant([
                    [110., 111.], [120.], [130.], [140., 141.]]),
                const.HIDDEN_STATE: tf.constant([[1.], [2.], [3.], [4.]]),
            })})
    return graph


class _MakeGraphTensorNodesOnly(tf.keras.layers.Layer):

  def call(self, inputs):
    return gt.GraphTensor.from_pieces(
        node_sets={
            "nodes": gt.NodeSet.from_fields(
                sizes=inputs["node_sizes"],
                features={
                    "dense": inputs["features_dense"],
                    const.HIDDEN_STATE: inputs["features"]},
            )
        },
    )


class ReadoutNamedTest(tf.test.TestCase, parameterized.TestCase):

  def testBasic(self):
    test_graph = gt.GraphTensor.from_pieces(
        node_sets={
            "users": gt.NodeSet.from_fields(
                sizes=tf.constant([3]),
                features={const.HIDDEN_STATE: tf.constant(
                    [[1., 1.],  # Read out as "source" 1.
                     [1., 2.],  # Read out as "source" 0.
                     [1., 3.]])}),
            "items": gt.NodeSet.from_fields(
                sizes=tf.constant([4]),
                features={const.HIDDEN_STATE: tf.constant(
                    [[2., 1.],
                     [2., 2.],  # Read out as "target" 1.
                     [2., 3.],  # Read out as "target" 3.
                     [2., 4.]])}),
            "_readout": gt.NodeSet.from_fields(
                sizes=tf.constant([2]),
                features={"labels": tf.constant([0, 1])})},
        edge_sets={
            "has_purchased": gt.EdgeSet.from_fields(
                sizes=tf.constant([2]),
                adjacency=adj.Adjacency.from_indices(
                    ("users", tf.constant([1, 2])),
                    ("items", tf.constant([0, 3])))),
            "_readout/source/1": gt.EdgeSet.from_fields(
                sizes=tf.constant([2]),
                adjacency=adj.Adjacency.from_indices(
                    # The "source" users are defined here.
                    ("users", tf.constant([1, 0])),
                    ("_readout", tf.constant([0, 1])))),
            "_readout/target/1": gt.EdgeSet.from_fields(
                sizes=tf.constant([2]),
                adjacency=adj.Adjacency.from_indices(
                    # The "target" items are defined here.
                    ("items", tf.constant([1, 2])),
                    ("_readout", tf.constant([0, 1]))))})
    expected_sources = [[1., 2.], [1., 1.]]
    expected_targets = [[2., 2.], [2., 3.]]

    # Test common usages that set the key exactly once.
    readout_source = graph_ops.ReadoutNamed("source")
    self.assertAllEqual(expected_sources, readout_source(test_graph))
    readout = graph_ops.ReadoutNamed()
    self.assertAllEqual(expected_sources, readout(test_graph, key="source"))
    self.assertAllEqual(expected_targets, readout(test_graph, key="target"))

    # Test setting the key not exactly once.
    # Redundant keys are ok.
    self.assertAllEqual(expected_sources,
                        readout_source(test_graph, key="source"))
    # No key is an error.
    with self.assertRaisesRegex(ValueError, r"requires a readout key"):
      _ = readout(test_graph)
    # Contradicting keys are an error, too.
    with self.assertRaisesRegex(ValueError, r"but called with"):
      _ = readout_source(test_graph, key="target")

  def testExplicitNames(self):
    test_graph = gt.GraphTensor.from_pieces(
        node_sets={
            "objects": gt.NodeSet.from_fields(
                sizes=tf.constant([2]),
                features={
                    "right_feature": tf.constant([[1., 1.], [1., 2.]]),
                    "wrong_feature": tf.constant([[9.], [9.]])}),
            "_out_it_reads_from_here": gt.NodeSet.from_fields(
                sizes=tf.constant([1]))},
        edge_sets={
            "relations": gt.EdgeSet.from_fields(
                sizes=tf.constant([1]),
                adjacency=adj.Adjacency.from_indices(
                    ("objects", tf.constant([1])),
                    ("objects", tf.constant([0])))),
            "_out_it_reads_from_here/widget": gt.EdgeSet.from_fields(
                sizes=tf.constant([1]),
                adjacency=adj.Adjacency.from_indices(
                    ("objects", tf.constant([1])),
                    ("_out_it_reads_from_here", tf.constant([0]))))})

    readout = graph_ops.ReadoutNamed(
        key="widget",
        feature_name="right_feature",
        readout_node_set="_out_it_reads_from_here",
        name="my_test_readout")
    self.assertAllEqual([[1., 2.]], readout(test_graph))

  def testTFLite(self):
    test_graph_readout_named_dict = {
        "nodes_users": tf.constant([
            [1.0, 1.0],  # Read out as "source" 1.
            [1.0, 2.0],  # Read out as "source" 0.
            [1.0, 3.0],
        ]),
        "nodes_items": tf.constant([
            [2.0, 1.0],
            [2.0, 2.0],  # Read out as "target" 1.
            [2.0, 3.0],  # Read out as "target" 3.
            [2.0, 4.0],
        ]),
        "nodes__readout": tf.constant([0, 1]),
        "edges_has_purchased_source": tf.constant([1, 2]),
        "edges_has_purchased_target": tf.constant([0, 3]),
        "edges__readout/source/1_source": tf.constant([1, 0]),
        "edges__readout/source/1_target": tf.constant([0, 1]),
        "edges__readout/target/1_source": tf.constant([1, 2]),
        "edges__readout/target/1_target": tf.constant([0, 1]),
    }
    inputs = {
        "nodes_users": tf.keras.Input(
            [2], None, "nodes_users", tf.float32
        ),
        "nodes_items": tf.keras.Input(
            [2], None, "nodes_items", tf.float32
        ),
        "nodes__readout": tf.keras.Input(
            [], None, "nodes__readout", tf.int32
        ),
        "edges_has_purchased_source": tf.keras.Input(
            [], None, "edges_has_purchased_source", tf.int32
        ),
        "edges_has_purchased_target": tf.keras.Input(
            [], None, "edges_has_purchased_target", tf.int32
        ),
        "edges__readout/source/1_source": tf.keras.Input(
            [], None, "edges__readout/source/1_source", tf.int32
        ),
        "edges__readout/source/1_target": tf.keras.Input(
            [], None, "edges__readout/source/1_target", tf.int32
        ),
        "edges__readout/target/1_source": tf.keras.Input(
            [], None, "edges__readout/target/1_source", tf.int32
        ),
        "edges__readout/target/1_target": tf.keras.Input(
            [], None, "edges__readout/target/1_target", tf.int32
        ),
    }
    graph_in = _MakeGraphTensorReadoutNamed()(inputs)
    readout = graph_ops.ReadoutNamed("source", name="test_readout_named")
    outputs = readout(graph_in)
    model = tf.keras.Model(inputs, outputs)
    expected = model(test_graph_readout_named_dict)

    # TODO(b/276291104): Remove when TF 2.11+ is required by all of TFGNN
    if tf.__version__.startswith("2.9.") or tf.__version__.startswith("2.10."):
      self.skipTest("GNN models are unsupported in TFLite until TF 2.11 but "
                    f"got TF {tf.__version__}")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    model_content = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=model_content)
    signature_runner = interpreter.get_signature_runner("serving_default")
    obtained = signature_runner(**test_graph_readout_named_dict)[
        "test_readout_named"
    ]
    self.assertAllEqual(expected, obtained)


# TODO(b/274779989): Replace this layer with a more standard representation
# of GraphTensor as a dict of plain Tensors.
class _MakeGraphTensorReadoutNamed(tf.keras.layers.Layer):

  def call(self, inputs):
    users_sizes = tf.shape(inputs["nodes_users"])[0]
    items_sizes = tf.shape(inputs["nodes_items"])[0]
    readout_sizes = tf.shape(inputs["nodes__readout"])[0]
    has_purchased_sizes = tf.shape(inputs["edges_has_purchased_source"])[0]
    readout_source_sizes = tf.shape(inputs["edges__readout/source/1_source"])[0]
    readout_target_sizes = tf.shape(inputs["edges__readout/target/1_target"])[0]
    return gt.GraphTensor.from_pieces(
        node_sets={
            "users": gt.NodeSet.from_fields(
                sizes=tf.expand_dims(users_sizes, axis=0),
                features={const.HIDDEN_STATE: inputs["nodes_users"]}),
            "items": gt.NodeSet.from_fields(
                sizes=tf.expand_dims(items_sizes, axis=0),
                features={const.HIDDEN_STATE: inputs["nodes_items"]}),
            "_readout": gt.NodeSet.from_fields(
                sizes=tf.expand_dims(readout_sizes, axis=0),
                features={"labels": inputs["nodes__readout"]})},
        edge_sets={
            "has_purchased": gt.EdgeSet.from_fields(
                sizes=tf.expand_dims(has_purchased_sizes, axis=0),
                adjacency=adj.Adjacency.from_indices(
                    ("users", inputs["edges_has_purchased_source"]),
                    ("items", inputs["edges_has_purchased_target"]))),
            "_readout/source/1": gt.EdgeSet.from_fields(
                sizes=tf.expand_dims(readout_source_sizes, axis=0),
                adjacency=adj.Adjacency.from_indices(
                    # The "source" users are defined here.
                    ("users", inputs["edges__readout/source/1_source"]),
                    ("_readout", inputs["edges__readout/source/1_target"]))),
            "_readout/target/1": gt.EdgeSet.from_fields(
                sizes=tf.expand_dims(readout_target_sizes, axis=0),
                adjacency=adj.Adjacency.from_indices(
                    # The "target" items are defined here.
                    ("items", inputs["edges__readout/target/1_source"]),
                    ("_readout", inputs["edges__readout/target/1_target"])))})


class BroadcastTest(tf.test.TestCase, parameterized.TestCase):

  def testFeatureName(self):
    red_values = [[11., 12.]]
    blue_values = [[21., 22.]]
    default_values = [[31., 32.]]
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(
            features={"red": tf.constant(red_values),
                      "blue": tf.constant(blue_values),
                      const.HIDDEN_STATE: tf.constant(default_values)}),
        node_sets={"nodes": gt.NodeSet.from_fields(
            sizes=tf.constant([2]), features={})})

    broadcast = graph_ops.Broadcast(const.CONTEXT, node_set_name="nodes",
                                    feature_name="red")
    self.assertEqual("red", broadcast.feature_name)
    self.assertAllEqual(red_values * 2, broadcast(graph))

    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      _ = broadcast(graph, feature_name="blue")

    self.assertAllEqual(
        default_values * 2,
        graph_ops.Broadcast(const.CONTEXT, node_set_name="nodes")(graph))

  @parameterized.named_parameters(
      ("ContextToNodes", const.CONTEXT, "nodes", [[10.], [10.], [10.]]),
      ("ContextToEdges", const.CONTEXT, "edges", [[10.], [10.]]),
      ("SourceToEdges", const.SOURCE, "edges", [[21.], [21.]]),
      ("TargetToEdges", const.TARGET, "edges", [[20.], [22.]]))
  def testTagAndLocation(self, tag, location, expected):
    values = dict(context=tf.constant([[10.]]),
                  nodes=tf.constant([[20. + k] for k in range(3)]),
                  edges=tf.constant([[30. + k] for k in range(2)]))
    graph = _make_test_graph_132(values)
    location_kwarg = (dict(node_set_name="nodes") if location == "nodes" else
                      dict(edge_set_name="edges"))

    # Initialized with all three args, called with zero to three (redundantly).
    broadcast = graph_ops.Broadcast(tag, feature_name="value", **location_kwarg)
    self.assertEqual(tag, broadcast.tag)
    self.assertEqual(location_kwarg, broadcast.location)
    self.assertAllEqual(expected, broadcast(graph))
    self.assertAllEqual(expected, broadcast(graph, tag=tag))
    self.assertAllEqual(expected, broadcast(graph, feature_name="value"))
    self.assertAllEqual(expected, broadcast(graph, **location_kwarg))
    self.assertAllEqual(expected, broadcast(graph, tag=tag,
                                            feature_name="value"))
    self.assertAllEqual(expected, broadcast(graph, tag=tag,
                                            **location_kwarg))
    self.assertAllEqual(expected, broadcast(graph, feature_name="value",
                                            **location_kwarg))
    self.assertAllEqual(expected, broadcast(graph, tag=tag,
                                            feature_name="value",
                                            **location_kwarg))

    # Initialized with one arg, called with the other two.
    broadcast = graph_ops.Broadcast(tag)
    self.assertEqual(tag, broadcast.tag)
    self.assertEqual({}, broadcast.location)
    self.assertAllEqual(expected, broadcast(graph, feature_name="value",
                                            **location_kwarg))

    broadcast = graph_ops.Broadcast(**location_kwarg)
    self.assertIsNone(broadcast.tag)
    self.assertEqual(location_kwarg, broadcast.location)
    self.assertAllEqual(expected, broadcast(graph, tag=tag,
                                            feature_name="value"))

    broadcast = graph_ops.Broadcast(feature_name="value")
    self.assertIsNone(broadcast.tag)
    self.assertEqual({}, broadcast.location)
    self.assertAllEqual(expected, broadcast(graph, tag=tag, **location_kwarg))

    # Initialized with zero args, called with all.
    broadcast = graph_ops.Broadcast()
    self.assertIsNone(broadcast.tag)
    self.assertEqual({}, broadcast.location)
    self.assertAllEqual(expected, broadcast(graph, tag=tag,
                                            feature_name="value",
                                            **location_kwarg))

  def testConflictingTag(self):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      broadcast = graph_ops.Broadcast(const.SOURCE, edge_set_name="wronk",
                                      feature_name="value")
      _ = broadcast(graph, tag=const.CONTEXT)

  @parameterized.named_parameters(
      ("Nodes", dict(node_set_name="nodes")),
      ("Edges", dict(edge_set_name="edges")))
  def testConflictingLocation(self, location_kwarg):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      broadcast = graph_ops.Broadcast(const.CONTEXT, node_set_name="wronk",
                                      feature_name="value")
      _ = broadcast(graph, feature_name="value", **location_kwarg)

  def testTooFewOrManyLocations(self):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, "at most one of"):
      graph_ops.Broadcast(const.CONTEXT,
                          node_set_name="nodes", edge_set_name="edges")
    with self.assertRaisesRegex(ValueError, "requires exactly one of"):
      graph_ops.Broadcast(const.CONTEXT)(graph)

  @parameterized.parameters(const.SOURCE, const.TARGET)
  def testNodeSetNameVsNonContext(self, origin):
    with self.assertRaisesRegex(ValueError, "requires edge_set_name"):
      graph_ops.Broadcast(origin, node_set_name="nodes")

  @parameterized.named_parameters(
      ("ContextToNodes", const.CONTEXT, "nodes", [[10.], [10.], [10.]]),
      ("ContextToEdges", const.CONTEXT, "edges", [[10.], [10.]]),
      ("SourceToEdges", const.SOURCE, "edges", [[21.], [21.]]),
      ("TargetToEdges", const.TARGET, "edges", [[20.], [22.]]))
  def testFromConfig(self, tag, location, expected):
    values = dict(context=tf.constant([[10.]]),
                  nodes=tf.constant([[20. + k] for k in range(3)]),
                  edges=tf.constant([[30. + k] for k in range(2)]))
    graph = _make_test_graph_132(values)
    location_kwarg = (dict(node_set_name="nodes") if location == "nodes" else
                      dict(edge_set_name="edges"))
    kwargs = dict(location_kwarg, tag=tag, feature_name="value",
                  name="test_broadcast")
    config = graph_ops.Broadcast(**kwargs).get_config()
    self.assertDictContainsSubset(kwargs, config)

    broadcast = graph_ops.Broadcast.from_config(config)
    self.assertEqual(tag, broadcast.tag)
    self.assertEqual("value", broadcast.feature_name)
    self.assertEqual(location_kwarg, broadcast.location)
    self.assertAllEqual(expected, broadcast(graph))

  @parameterized.named_parameters(
      ("ContextToNodes", const.CONTEXT, "nodes"),
      ("ContextToEdges", const.CONTEXT, "edges"),
      ("SourceToEdges", const.SOURCE, "edges"),
      ("TargetToEdges", const.TARGET, "edges"))
  def testTFLite(self, tag, location):
    values = dict(context=tf.constant([[10.]]),
                  nodes=tf.constant([[20. + k] for k in range(3)]),
                  edges=tf.constant([[30. + k] for k in range(2)]))
    test_graph_132_dict = {
        "nodes_value": values["nodes"],
        "edges_value": values["edges"],
        "context_value": values["context"],
        "source": tf.constant([1, 1]),
        "target": tf.constant([0, 2]),
    }
    inputs = {
        "nodes_value": tf.keras.Input([1], None, "nodes_value", tf.float32),
        "edges_value": tf.keras.Input([1], None, "edges_value", tf.float32),
        "context_value": tf.keras.Input([1], None, "context_value", tf.float32),
        "source": tf.keras.Input([], None, "source", tf.int32),
        "target": tf.keras.Input([], None, "target", tf.int32),
    }
    location_kwarg = (dict(node_set_name="nodes") if location == "nodes" else
                      dict(edge_set_name="edges"))
    kwargs = dict(location_kwarg, tag=tag, feature_name="value",
                  name="test_broadcast")
    graph_in = _MakeGraphTensor()(inputs)
    broadcast = graph_ops.Broadcast(**kwargs)
    outputs = broadcast(graph_in)
    model = tf.keras.Model(inputs, outputs)
    expected = model(test_graph_132_dict)

    # TODO(b/276291104): Remove when TF 2.11+ is required by all of TFGNN
    if tf.__version__.startswith("2.9.") or tf.__version__.startswith("2.10."):
      self.skipTest("GNN models are unsupported in TFLite until TF 2.11 but "
                    f"got TF {tf.__version__}")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    model_content = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=model_content)
    signature_runner = interpreter.get_signature_runner("serving_default")
    obtained = signature_runner(**test_graph_132_dict)["test_broadcast"]
    self.assertAllEqual(expected, obtained)


def _make_test_graph_132(values):
  """Returns GraphTensor for [v0] <-e0-- [v1] --e1--> [v2] with values."""
  def maybe_features(key):
    return dict(features={"value": values[key]} if key in values else {})
  graph = gt.GraphTensor.from_pieces(
      context=gt.Context.from_fields(**maybe_features("context")),
      node_sets={"nodes": gt.NodeSet.from_fields(
          sizes=tf.constant([3]), **maybe_features("nodes"))},
      edge_sets={"edges": gt.EdgeSet.from_fields(
          sizes=tf.constant([2]),
          adjacency=adj.Adjacency.from_indices(("nodes", tf.constant([1, 1])),
                                               ("nodes", tf.constant([0, 2]))),
          **maybe_features("edges"))})
  return graph


class AddSelfLoopsTest(tf.test.TestCase, parameterized.TestCase):
  """Ensures that AddSelfLoops invokes well-tested function add_self_loops."""

  def testAddSelfLoopLayerCallAddSelfLoopsFnReturningItsValue(self):
    mock.MagicMock()
    with mock.patch.object(
        graph_ops.ops, "add_self_loops", autospec=True) as mock_one:
      mock_one.return_value = "testReturn"

      layer = graph_ops.AddSelfLoops("some_edge_set")
      self.assertEqual("testReturn", layer("some_graph_tensor"))
      mock_one.assert_called_once_with("some_graph_tensor", "some_edge_set")

  def testTFLite(self):
    values = dict(
        context=tf.constant([[1.0, 1.5]]),
        nodes=tf.constant([[11.0 + v, 11.5 + v] for v in range(3)]),
        edges=tf.constant([[21.0 + v, 21.5 + v] for v in range(4)]))
    test_graph_134_dict = {
        "nodes_value": values["nodes"],
        "edges_value": values["edges"],
        "context_value": values["context"],
        "source": tf.constant([0, 1, 1, 2]),
        "target": tf.constant([1, 0, 2, 1]),
    }
    inputs = {
        "nodes_value": tf.keras.Input([2], None, "nodes_value", tf.float32),
        "edges_value": tf.keras.Input([2], None, "edges_value", tf.float32),
        "context_value": tf.keras.Input([2], None, "context_value", tf.float32),
        "source": tf.keras.Input([], None, "source", tf.int32),
        "target": tf.keras.Input([], None, "target", tf.int32),
    }
    graph_in = _MakeGraphTensor()(inputs)
    layer = graph_ops.AddSelfLoops("edges")
    graph_out = layer(graph_in)
    outputs = tf.keras.layers.Layer(name="final_edge_states")(
        graph_out.edge_sets["edges"].features["value"]
    )
    model = tf.keras.Model(inputs, outputs)
    expected = model(test_graph_134_dict).numpy()

    # TODO(b/276291104): Remove when TF 2.11+ is required by all of TFGNN
    if tf.__version__.startswith("2.9.") or tf.__version__.startswith("2.10."):
      self.skipTest("GNN models are unsupported in TFLite until TF 2.11 but "
                    f"got TF {tf.__version__}")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    model_content = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=model_content)
    signature_runner = interpreter.get_signature_runner("serving_default")
    obtained = signature_runner(**test_graph_134_dict)["final_edge_states"]
    self.assertAllEqual(expected, obtained)


class PoolTest(tf.test.TestCase, parameterized.TestCase):

  def testFeatureName(self):
    red_values = [[11., 12.], [13., 14]]
    blue_values = [[21., 22.], [23., 24]]
    default_values = [[31., 32.], [33., 34.]]
    graph = gt.GraphTensor.from_pieces(
        node_sets={"nodes": gt.NodeSet.from_fields(
            sizes=tf.constant([2]),
            features={"red": tf.constant(red_values),
                      "blue": tf.constant(blue_values),
                      const.HIDDEN_STATE: tf.constant(default_values)})})

    pool = graph_ops.Pool(const.CONTEXT, "sum", node_set_name="nodes",
                          feature_name="red")
    self.assertEqual("red", pool.feature_name)
    self.assertAllEqual([[24., 26.]], pool(graph))

    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      _ = pool(graph, feature_name="blue")

    self.assertAllEqual(
        [[64., 66.]],
        graph_ops.Pool(const.CONTEXT, "sum", node_set_name="nodes")(graph))

  @parameterized.parameters(("sum", [[12.+14., 11+13.]]),
                            ("mean", [[13., 12.]]),
                            ("max", [[14., 13.]]),
                            ("min", [[12., 11.]]))
  def testReduceType(self, reduce_type, expected):
    values = [[12., 11.],
              [14., 13.]]
    graph = gt.GraphTensor.from_pieces(
        node_sets={"nodes": gt.NodeSet.from_fields(
            sizes=tf.constant([2]),
            features={const.HIDDEN_STATE: tf.constant(values)})})

    pool = graph_ops.Pool(const.CONTEXT, node_set_name="nodes")
    self.assertIsNone(pool.reduce_type)
    self.assertAllEqual(expected, pool(graph, reduce_type=reduce_type))

    with self.assertRaisesRegex(ValueError, r"requires reduce_type"):
      _ = pool(graph)

    pool = graph_ops.Pool(const.CONTEXT, reduce_type, node_set_name="nodes")
    self.assertEqual(reduce_type, pool.reduce_type)
    self.assertAllEqual(expected, pool(graph))
    self.assertAllEqual(expected, pool(graph, reduce_type=reduce_type))

    other = "max" if reduce_type != "max" else "min"
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      _ = pool(graph, reduce_type=other)

  @parameterized.named_parameters(
      ("NodesToContext", const.CONTEXT, "nodes", "sum", [[20. + 21. + 22.]]),
      ("EdgesToContext", const.CONTEXT, "edges", "sum", [[30. + 31.]]),
      ("EdgesToSource", const.SOURCE, "edges", "sum", [[0.], [30.+31.], [0.]]),
      ("EdgesToTarget", const.TARGET, "edges", "sum", [[30.], [0.], [31.]]))
  def testTagAndLocation(self, tag, location, reduce_type, expected):
    values = dict(context=tf.constant([[10.]]),
                  nodes=tf.constant([[20. + k] for k in range(3)]),
                  edges=tf.constant([[30. + k] for k in range(2)]))
    graph = _make_test_graph_132(values)
    location_kwarg = (dict(node_set_name="nodes") if location == "nodes" else
                      dict(edge_set_name="edges"))

    # Initialized with all four args, called with zero, one or all args.
    pool = graph_ops.Pool(tag, reduce_type, feature_name="value",
                          **location_kwarg)
    self.assertEqual(tag, pool.tag)
    self.assertEqual(location_kwarg, pool.location)
    self.assertAllEqual(expected, pool(graph))
    self.assertAllEqual(expected, pool(graph, tag=tag))
    self.assertAllEqual(expected, pool(graph, reduce_type=reduce_type))
    self.assertAllEqual(expected, pool(graph, feature_name="value"))
    self.assertAllEqual(expected, pool(graph, **location_kwarg))
    self.assertAllEqual(expected, pool(graph, tag=tag, reduce_type=reduce_type,
                                       feature_name="value", **location_kwarg))

    # Initialized with one arg, called with the other three.
    pool = graph_ops.Pool(tag)
    self.assertEqual(tag, pool.tag)
    self.assertEqual({}, pool.location)
    self.assertAllEqual(expected, pool(graph, reduce_type=reduce_type,
                                       feature_name="value", **location_kwarg))

    pool = graph_ops.Pool(reduce_type=reduce_type)
    self.assertIsNone(pool.tag)
    self.assertEqual({}, pool.location)
    self.assertAllEqual(expected, pool(graph, tag=tag,
                                       feature_name="value", **location_kwarg))

    pool = graph_ops.Pool(**location_kwarg)
    self.assertIsNone(pool.tag)
    self.assertEqual(location_kwarg, pool.location)
    self.assertAllEqual(expected, pool(graph, tag=tag, reduce_type=reduce_type,
                                       feature_name="value"))

    pool = graph_ops.Pool(feature_name="value")
    self.assertIsNone(pool.tag)
    self.assertEqual({}, pool.location)
    self.assertAllEqual(expected, pool(graph, tag=tag, reduce_type=reduce_type,
                                       **location_kwarg))

    # Initialized with zero args, called with all.
    pool = graph_ops.Pool()
    self.assertIsNone(pool.tag)
    self.assertEqual({}, pool.location)
    self.assertAllEqual(expected, pool(graph, tag=tag, reduce_type=reduce_type,
                                       feature_name="value", **location_kwarg))

  def testConflictingTag(self):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      pool = graph_ops.Pool(const.SOURCE, "sum", edge_set_name="wronk",
                            feature_name="value")
      _ = pool(graph, tag=const.CONTEXT)

  @parameterized.named_parameters(
      ("Nodes", dict(node_set_name="nodes")),
      ("Edges", dict(edge_set_name="edges")))
  def testConflictingLocation(self, location_kwarg):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, r"initialized .* but called with"):
      pool = graph_ops.Pool(const.CONTEXT, "sum", node_set_name="wronk",
                            feature_name="value")
      _ = pool(graph, feature_name="value", **location_kwarg)

  def testTooFewOrManyLocations(self):
    graph = gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(features={"value": tf.constant([[0.]])}))
    with self.assertRaisesRegex(ValueError, "at most one of"):
      graph_ops.Pool(const.CONTEXT, "sum", node_set_name="nodes",
                     edge_set_name="edges")
    with self.assertRaisesRegex(ValueError, "requires exactly one of"):
      graph_ops.Pool(const.CONTEXT, "sum")(graph)

  @parameterized.parameters(const.SOURCE, const.TARGET)
  def testNodeSetNameVsNonContext(self, origin):
    with self.assertRaisesRegex(ValueError, "requires edge_set_name"):
      graph_ops.Pool(origin, "sum", node_set_name="nodes")

  @parameterized.named_parameters(
      ("NodesToContext", const.CONTEXT, "nodes", "mean", [[(20.+21.+22.)/3.]]),
      ("EdgesToContext", const.CONTEXT, "edges", "max", [[31.]]),
      ("EdgesToSource", const.SOURCE, "edges", "sum", [[0.], [30.+31.], [0.]]),
      ("EdgesToTarget", const.TARGET, "edges", "sum", [[30.], [0.], [31.]]))
  def testFromConfig(self, tag, location, reduce_type, expected):
    values = dict(context=tf.constant([[10.]]),
                  nodes=tf.constant([[20. + k] for k in range(3)]),
                  edges=tf.constant([[30. + k] for k in range(2)]))
    graph = _make_test_graph_132(values)
    location_kwarg = (dict(node_set_name="nodes") if location == "nodes" else
                      dict(edge_set_name="edges"))
    kwargs = dict(location_kwarg, reduce_type=reduce_type, tag=tag,
                  feature_name="value", name="test_pool")
    config = graph_ops.Pool(**kwargs).get_config()
    self.assertDictContainsSubset(kwargs, config)

    pool = graph_ops.Pool.from_config(config)
    self.assertEqual(tag, pool.tag)
    self.assertEqual(reduce_type, pool.reduce_type)
    self.assertEqual("value", pool.feature_name)
    self.assertEqual(location_kwarg, pool.location)
    self.assertAllEqual(expected, pool(graph))

  @parameterized.named_parameters(
      ("NodesToContext", const.CONTEXT, "nodes", "mean"),
      ("EdgesToContext", const.CONTEXT, "edges", "max"),
      ("EdgesToContextMaxNoInf", const.CONTEXT, "edges", "max_no_inf"),
      ("EdgesToSource", const.SOURCE, "edges", "sum"),
      ("EdgesToTarget", const.TARGET, "edges", "sum"))
  def testTFLite(self, tag, location, reduce_type):
    values = dict(context=tf.constant([[10.]]),
                  nodes=tf.constant([[20. + k] for k in range(3)]),
                  edges=tf.constant([[30. + k] for k in range(2)]))
    test_graph_132_dict = {
        "nodes_value": values["nodes"],
        "edges_value": values["edges"],
        "context_value": values["context"],
        "source": tf.constant([1, 1]),
        "target": tf.constant([0, 2]),
    }
    inputs = {
        "nodes_value": tf.keras.Input([1], None, "nodes_value", tf.float32),
        "edges_value": tf.keras.Input([1], None, "edges_value", tf.float32),
        "context_value": tf.keras.Input([1], None, "context_value", tf.float32),
        "source": tf.keras.Input([], None, "source", tf.int32),
        "target": tf.keras.Input([], None, "target", tf.int32),
    }
    location_kwarg = (dict(node_set_name="nodes") if location == "nodes" else
                      dict(edge_set_name="edges"))
    kwargs = dict(location_kwarg, reduce_type=reduce_type, tag=tag,
                  feature_name="value", name="test_pool")
    graph_in = _MakeGraphTensor()(inputs)
    pool = graph_ops.Pool(**kwargs)
    outputs = pool(graph_in)
    model = tf.keras.Model(inputs, outputs)
    expected = model(test_graph_132_dict)

    # TODO(b/276291104): Remove when TF 2.11+ is required by all of TFGNN
    if tf.__version__.startswith("2.9.") or tf.__version__.startswith("2.10."):
      self.skipTest("GNN models are unsupported in TFLite until TF 2.11 but "
                    f"got TF {tf.__version__}")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    model_content = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=model_content)
    signature_runner = interpreter.get_signature_runner("serving_default")
    obtained = signature_runner(**test_graph_132_dict)["test_pool"]
    self.assertAllEqual(expected, obtained)


# TODO(b/274779989): Replace this layer with a more standard representation
# of GraphTensor as a dict of plain Tensors.
class _MakeGraphTensor(tf.keras.layers.Layer):

  def call(self, inputs):
    node_sizes = tf.shape(inputs["nodes_value"])[0]
    edge_sizes = tf.shape(inputs["edges_value"])[0]
    return gt.GraphTensor.from_pieces(
        context=gt.Context.from_fields(
            features={"value": inputs["context_value"]}),
        node_sets={
            "nodes": gt.NodeSet.from_fields(
                sizes=tf.expand_dims(node_sizes, axis=0),
                features={"value": inputs["nodes_value"]},
            )
        },
        edge_sets={
            "edges": gt.EdgeSet.from_fields(
                sizes=tf.expand_dims(edge_sizes, axis=0),
                adjacency=adj.Adjacency.from_indices(
                    ("nodes", inputs["source"]), ("nodes", inputs["target"])
                ),
                features={"value": inputs["edges_value"]},
            )
        },
    )

if __name__ == "__main__":
  tf.test.main()
