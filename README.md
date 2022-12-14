# Chemingon
Chemingon provides a handy framework for parallel lab automations.
Unlike conventional lab automation systems, where the operations are conducted sequentially,
with the help of Chemingon, multiple reactions can be done on the same apparatus efficiently in a parallel manner. 
Features: 
- Automated task scheduling 
- User extensibility
- User-friendly GUI for protocol execution, progress monitering, and data visualisation

## Usage
The GUI of Chemingon is based on Jupyter notebook and Jupyter Widgets, 
so do make sure you have them installed.

### Component
The first step to begin with is to define the components. These are the instruments to be used in the experiment,
for example, pumps, auto-samplers, sensors, etc. Although a limited number of components have been provided, new 
components can be custom defined by inheriting the Component, Sensor, and CombinedComponent classes, depend on the
type of the equipment.

For a simple demonstration, we can define some dummy components here:
```python
from Chemingon import DummyComponent, DummySensor, DummyCombinedDevice

dumComp1 = DummyComponent("dum1")
dumComp2 = DummyComponent("dum2")
dumComp3 = DummyComponent("dum3")
dumComp4 = DummyComponent("dum4")
dumComp5 = DummyComponent('dum5')
dumSens = DummySensor('sens1', freq = 1)
dumSens2 = DummySensor('sens2', freq = 1)
dumCombComp = DummyCombinedDevice('dummy combined')

publicComp = DummyComponent("Public Dum", is_public=True)
```
It is fairly easy to understand that the names of the components are declared, and the data sampling frequencies are
defined for sensors, but the last component is defined as a public component by setting the 'is_public' option as True.
This is a crucial feature to implement multichannel reactions and will be explained later.

### Apparatus
With the components defined, we can now move on to creating an `Apparatus`, which contains all components used in 
the experiment:
```python
from Chemingon import Apparatus

apparatus_test = Apparatus("dummy test")

comList = [dumComp1, dumComp2, dumComp3, dumComp4, dumSens,dumSens2, dumCombComp]
apparatus_test.add_component_list(comList)

apparatus_test.add_component(publicComp)
```
As demonstrated above, there are two methods for adding components to an `Apparatus`. The `add_component_list()` method 
takes in a list of components, while the `.add_component()` method receives a single component.

### Operation and Protocol
To inform the program about how the experiments are conducted, we have to save a series of `Operation` in a `Protocol` object. 
An `Operation` is a single movement of a component. The command, which is a method defined in the component's class, is passed
as a string, followed by the arguments as a dictionary. The wait option is True by default, where the following steps are
executed after the operation is done; however, by setting it to False, one can still wait for it using a VirtualOperation 
"wait_for_operation" as shown below. The `Operation` object can be added to a `Protocol` using the method `add_single_operation()`,
or a shortcut `quick_add()` can be used without the need to define an `Operation` object. The operations must be added in 
the order of execution.

```python
from Chemingon import Protocol, VirtualOperation, Operation

# defining the Protocol
protocol_test1 = Protocol(apparatus_test, "test protocol1")

# add a delay operation, which is a VirtualOperation
protocol_test1.add_single_operation(VirtualOperation("delay", kwargs={"seconds": 1}))

# define and add an Operation to the Protocol
op1 = Operation(publicComp, "do_something", wait=False, kwargs={"output": "protocol 1 public device"})
protocol_test1.add_single_operation(op1)

# wait until op1 is done
protocol_test1.add_single_operation(VirtualOperation("wait_for_operation", kwargs={"op": op1}))

# quick_add() is a shortcut for adding a simple operation to a Protocol
protocol_test1.quick_add(dumComp1, "do_something", kwargs={"output": "protocol 1"})
protocol_test1.quick_add(publicComp, 'do_something', kwargs = {'output': 'protocol1 public'})

protocol_test2 = Protocol(apparatus_test, "test protocol2")
protocol_test2.add_single_operation(VirtualOperation("delay", kwargs={"seconds": 1}))
protocol_test2.quick_add(publicComp, 'do_something', kwargs = {'output': 'protocol2 public'})
protocol_test2.quick_add(dumComp2, "do_something", kwargs={"output": "protocol 2"})
protocol_test2.quick_add(dumComp2, "do_something", kwargs={"output": "protocol 2-2"})
protocol_test2.quick_add(publicComp, 'do_something', kwargs = {'output': 'protocol2 public'})
```
`Protocol` can also be added to another `Protocol` as a sub protocol using `add_sub_protocol()`.

### Experiment
The final step is to create an `Experiment` object, which puts everything we have defined previously together and 
execute the experiment. It is required to define the number of channels for the `Experiment`. The protocols can then be
added to each channel of the experiment.
```python
from Chemingon import Experiment
exp = Experiment(apparatus_test, channels=2, keep_running=False)
exp.add_protocol(protocol_test1, channel=1)
exp.add_protocol(protocol_test2, channel=2)
```

Finally, simply start the graphical user interface:
```python
exp.start_jupyter_ui()
```
Click the "Start" button to commence. The log file and data files are saved in the "experiment_results" folder in the same 
directory as you .ipynb file.

## Example of Jupyter UI
![image](https://github.com/MuyeX/Chemingon-master/blob/main/example_pics/GUI_running_1.png)
![image](https://github.com/MuyeX/Chemingon-master/blob/main/example_pics/GUI_running_2.png)

## How are the tasks scheduled?
Remember that we have defined several channels when creating our `Experiment`? Basically, the operations and protocols
are executed sequentially within a channel, while different channels run in parallel.

In the simplest situation, each channel has its own instruments and does not interfere with other channels. But in 
reality, the instrument required for certain steps is often shared between the channels. For example, an HPLC can be
shared by everyone in the lab for various projects. In such cases, Chemingon applies a first come, first served system.
Upon creation, the "is_public" tag of each component could be set, which is by default False. According to the tag,
all components are divided into public components, which are shared by all channels, and private components, fully
occupied by the channel and does not interfere with others. When an operation involving a public component is reached, 
it queues up at the point and wait to be done before moving on.

For more exquisite controls of the schedule, the `block_public` argument is introduced for sub-protocol. When the 
`block_public` option is True, the sub-protocol will fully occupy the public components used during the period of
execution. In other words, no other operations is executed on these components from the beginning to the end of the 
sub-protocol.

## Work safely
Keep an eye on your apparatus in case any error occurs. To reduce the errors in the codes, it is recommended
to validate the protocols using the dry-run option before actual testing with the instruments.

## More
More instructions and contents on error handling, APIs for customised components, protocols input from files, 
etc. to be added.