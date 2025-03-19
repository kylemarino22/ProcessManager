import importlib

def load_json(filename):
    import json
    with open(filename, 'r') as f:
        return json.load(f)
    
def dynamic_import(func_path):
    """
    Dynamically import a function from a module.
    For example, given "path.to.module.func_name", it returns the function object.
    """
    module_path, func_name = func_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)
