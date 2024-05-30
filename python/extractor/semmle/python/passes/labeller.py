# Label an AST with symbol-tables.
# Follow ordering specified in Python/symtable.c

from semmle.python import ast

from semmle.python.passes.ast_pass import iter_fields, ASTVisitor

__all__ = [ 'Labeller' ]

class SymbolTable(ASTVisitor):
    '''A symbol table for a Python scope.
    Records uses and definitions, `global` and `nonlocal` statements for names in that scope'''

    def __init__(self, scope):
        self.definitions = set()
        self.uses = set()
        self.declared_as_global = set()
        self.declared_as_nonlocal = set()
        for _, _, child in iter_fields(scope):
            self.visit(child)

    def visit_Class(self, node):
        pass

    def visit_Function(self, node):
        pass

    def visit_Name(self, node):
        name = node.variable.id
        if isinstance(node.ctx, ast.Load):
            self.uses.add(name)
        elif isinstance(node.ctx, (ast.Store, ast.Param, ast.Del)):
            self.definitions.add(name)
        else:
            raise Exception("Unknown context for name: %s" % node.ctx)

    def visit_Global(self, node):
        self.declared_as_global.update(node.names)

    def visit_Nonlocal(self, node):
        self.declared_as_nonlocal.update(node.names)

    def is_bound(self, name):
        declared_free = name in self.declared_as_global or name in self.declared_as_nonlocal
        return name in self.definitions and not declared_free

class _LabellingContext(ASTVisitor):

    def __init__(self, scope, module = None, outer = None):
        '''Create a labelling context for `scope`. `module` is the module containing the scope,
        and outer is the enclosing context, if any'''
        self.symbols = SymbolTable(scope)
        self.scope = scope
        self.outer = outer
        if module is None:
            module = scope
        self.module = module

    def label(self):
        'Label the node with this context'
        self.visit(self.module)

    def visit_Function(self, node):
        sub_context = _LabellingContext(node, self.module, self)
        for _, _, child in iter_fields(node):
            sub_context.visit(child)

    visit_Class = visit_Function

    def visit_Variable(self, node):
        if node.scope is not None:
            return
        name = node.id
        if name in self.symbols.declared_as_global:
            node.scope = self.module
        elif self.symbols.is_bound(name):
            node.scope = self.scope
        else: # Free variable, either implicitly or explicitly via nonlocal.
            outer = self.outer
            while outer is not None:
                if isinstance(outer.scope, ast.Class):
                    # in the code example below, the use of `baz` inside `func` is NOT a reference to the
                    # function defined on the class, but is a reference to a global variable.
                    #
                    # The use of `baz` on class scope -- `bazzed = baz("class-scope")`
                    # -- is a reference to the function defined on the
                    #
                    # ```py
                    # class Foo
                    #     def baz(arg):
                    #         return arg + "-baz"
                    #     def func(self):
                    #         return baz("global-scope")
                    #     bazzed = baz("class-scope")
                    # ```
                    #
                    # So we skip over class scopes.
                    #
                    # See ql/python/ql/test/library-tests/variables/scopes/in_class.py
                    # added in https://github.com/github/codeql/pull/10171
                    pass
                elif outer.symbols.is_bound(name):
                    node.scope = outer.scope
                    break
                outer = outer.outer
            else:
                node.scope = self.module

class Labeller(object):
    '''Labels the ast using symbols generated by the symtable module'''

    def apply(self, module):
        'Apply this Labeller to the module'
        #Ensure that AST root nodes have a globally consistent identifier
        if module.ast is None:
            return
        _LabellingContext(module.ast).label()
