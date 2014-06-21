#! /usr/bin/env python

##############################################################################
##  DendroPy Phylogenetic Computing Library.
##
##  Copyright 2010-2014 Jeet Sukumaran and Mark T. Holder.
##  All rights reserved.
##
##  See "LICENSE.txt" for terms and conditions of usage.
##
##  If you use this work or any portion thereof in published work,
##  please cite it as:
##
##     Sukumaran, J. and M. T. Holder. 2010. DendroPy: a Python library
##     for phylogenetic computing. Bioinformatics 26: 1569-1571.
##
##############################################################################

"""
This module defines the :class:`DataSet`: a top-level data container object
that manages collections of :class:`TaxonNamespace`, :class:`TreeList`, and
(various kinds of) :class:`CharacterMatrix` objects.
"""

import warnings
try:
    from StringIO import StringIO # Python 2 legacy support: StringIO in this module is the one needed (not io)
except ImportError:
    from io import StringIO # Python 3
import copy
import sys
from dendropy.utility import container
from dendropy.utility import error
from dendropy.datamodel import basemodel
from dendropy.datamodel import taxonmodel
from dendropy.datamodel import treemodel
from dendropy.datamodel import charmatrixmodel
from dendropy.datamodel import charstatemodel
from dendropy import dataio

###############################################################################
## DataSet

class DataSet(
        basemodel.Annotable,
        basemodel.Readable,
        basemodel.Writeable,
        basemodel.DataObject):
    """
    A phylogenetic data object that coordinates collections of
    :class:`TaxonNamespace`, :class:`TreeList`, and (various kinds of)
    :class:`CharacterMatrix` objects.

    A :class:`DataSet` has three attributes:

        `taxon_namespaces`
            A list of :class:`TaxonNamespace` objects, each representing
            a distinct namespace for operational taxononomic unit concept
            definitions.

        `tree_lists`
            A list of :class:`TreeList` objects, each representing a
            collection of :class:`Tree` objects.

        `char_matrices`
            A list of :class:`CharacterMatrix`-derived objects (e.g.
            :class:`DnaCharacterMatrix`).

    Multiple :class:`TaxonNamespace` objects within a :class:`DataSet` are
    allowed so as to support reading/loading of data from external sources that
    have multiple independent taxon namespaces defined within the same source
    or document (e.g., a Mesquite file with multiple taxa blocks, or a NeXML
    file with multiple OTU sections). Ideally, however, this would not
    be how data is managed. Recommended idiomatic usage would be to use a
    :class:`DataSet` to manage multiple types of data that all share and
    reference the same, single taxon namespace.

    Note that unless there is a need to collect and serialize a collection of
    data to the same file or external source, it is probably better
    semantically to use more specific data structures (e.g., a
    :class:`TreeList` object for trees or a :class:`DnaCharacterMatrix`
    object for an alignment). Similarly, when deserializing an external
    data source, if just a single type or collection of data is needed (e.g.,
    the collection of trees from a file that includes both trees and an
    alignment), then it is semantically cleaner to deserialize the data
    into a more specific structure (e.g., a :class:`TreeList` to get all the
    trees). However, when deserializing a mixed external data source
    with, e.g. multiple alignments or trees and one or more alignments, and you
    need to access/use more than a single collection, it is more efficient to
    read the entire data source at once into a :class:`DataSet` object and then
    independently extract the data objects as you need them from the various
    collections.

    """

    def _parse_from_stream(cls,
            stream,
            schema,
            **kwargs):
        """
        Constructs a new :class:`DataSet` object and populates it with data
        from file-like object `stream`.
        """
        exclude_trees = kwargs.pop("exclude_trees", False)
        exclude_chars = kwargs.pop("exclude_chars", False)
        taxon_namespace = taxonmodel.process_kwargs_dict_for_taxon_namespace(kwargs, None)
        label = kwargs.pop("label", None)
        dataset = DataSet(label=label)
        reader = dataio.get_reader(schema, **kwargs)
        reader.read_dataset(
                stream=stream,
                dataset=dataaset,
                taxon_namespace=taxon_namespace,
                exclude_trees=exclude_trees,
                exclude_chars=exclude_chars,
                state_alphabet_factory=charstatemodel.StateAlphabet,
                )
        return dataset
    _parse_from_stream = classmethod(_parse_from_stream)

    ###########################################################################
    ### Lifecycle and Identity

    def __init__(self, *args, **kwargs):
        """
        The constructor can take one argument. This can either be another
        :class:`DataSet` instance or an iterable of :class:`TaxonNamespace`,
        :class:`TreeList`, or :class:`CharacterMatrix`-derived instances.

        In the former case, the newly-constructed :class:`DataSet` will be a
        shallow-copy clone of the argument.

        In the latter case, the newly-constructed :class:`DataSet` will have
        the elements of the iterable added to the respective collections
        (``taxon_namespaces``, ``tree_lists``, or ``char_matrices``, as
        appropriate). This is essentially like calling :meth:`DataSet.add()`
        on each element separately.
        """
        if len(args) > 1:
            # only allow 1 positional argument
            raise error.TooManyArgumentsError(func_name=self.__class__.__name__, max_args=1, args=args)
        if "stream" in kwargs or "schema" in kwargs:
            raise TypeError("Constructing from an external stream is no longer supported: use the factory method 'DataSet.get_from_stream()'")
        elif len(args) == 1 and isinstance(args[0], DataSet):
            self._clone_from(args[0], kwargs)
        else:
            basemodel.DataObject.__init__(self, label=kwargs.pop("label", None))
            self.taxon_namespaces = container.OrderedSet()
            self.tree_lists = container.OrderedSet()
            self.char_matrices = container.OrderedSet()
            self.attached_taxon_namespace = None
            self._process_taxon_namespace_directives(kwargs)
            self.comments = []
            if len(args) == 1 and not isinstance(args[0], DataSet):
                for item in args[0]:
                    self.add(item)
        if kwargs:
            raise TypeError("Unrecognized or unsupported arguments: {}".format(kwargs))

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other

    def _clone_from(self, dataset, kwargs_dict):
        raise NotImplementedError

    def __copy__(self):
        raise NotImplementedError

    def taxon_namespace_scoped_copy(self, memo=None):
        raise NotImplementedError

    def __deepcopy__(self, memo=None):
        raise NotImplementedError

    ###########################################################################
    ### Data I/O

    def read(self,
            stream,
            schema,
            **kwargs):
        exclude_trees = kwargs.pop("exclude_trees", False)
        exclude_chars = kwargs.pop("exclude_chars", False)
        taxon_namespace = taxonmodel.process_kwargs_dict_for_taxon_namespace(kwargs, None)
        if (self.attached_taxon_namespace is not None
                and taxon_namespace is not None
                and self.attached_taxon_namespace is not taxon_namespace):
            raise ValueError("DataSet has attached TaxonNamespace that is not the same as `taxon_namespace`")
        if self.attached_taxon_namespace is not None and taxon_namespace is None:
            taxon_namespace = self.attached_taxon_namespace
        label = kwargs.pop("label", None)
        reader = dataio.get_reader(schema, **kwargs)
        n_tns = len(self.taxon_namespaces)
        n_tree_lists = len(self.tree_lists)
        n_char_matrices = len(self.char_matrices)
        reader.read_dataset(
                stream=stream,
                dataset=self,
                taxon_namespace=taxon_namespace,
                exclude_trees=exclude_trees,
                exclude_chars=exclude_chars,
                state_alphabet_factory=charstatemodel.StateAlphabet,
                )
        n_tns2 = len(self.taxon_namespaces)
        n_tree_lists2 = len(self.tree_lists)
        n_char_matrices2 = len(self.char_matrices)
        return (n_tns2-n_tns,
                n_tree_lists2-n_tree_lists,
                n_char_matrices2-n_char_matrices)

    ###########################################################################
    ### Domain Data Management

    ### General ###

    def add(self, data_object, **kwargs):
        """
        Generic add for TaxonNamespace, TreeList or CharacterMatrix objects.
        """
        if isinstance(data_object, taxonmodel.TaxonNamespace):
            self.add_taxon_set(data_object)
        elif isinstance(data_object, treemodel.TreeList):
            self.add_tree_list(data_object)
        elif isinstance(data_object, charmatrixmodel.CharacterMatrix):
            self.add_char_matrix(data_object)
        else:
            raise error.InvalidArgumentValueError("Cannot add object of type {} to DataSet" .format(type(data_object)))

    ### TaxonNamespace ###

    def add_taxon_namespace(self, taxon_namespace):
        """
        Adds a taxonomic unit concept namespace represented by a
        :class:`TaxonNamespace` instance to this dataset if it is not already
        there.

        Parameters
        ----------
        taxon_namespace : :class:`TaxonNamespace`
            The :class:`TaxonNamespace` object to be added.
        """
        self.taxon_namespaces.add(taxon_namespace)
        return taxon_namespace

    def new_taxon_namespace(self, *args, **kwargs):
        """
        Creates a new `TaxonNamespace` object, according to the arguments given
        (passed to `TaxonNamespace()`), and adds it to this `DataSet`.
        """
        t = taxonmodel.TaxonNamespace(*args, **kwargs)
        self.add_taxon_namespace(t)
        return t

    def attach_taxon_namespace(self, taxon_namespace=None):
        """
        Forces all read() calls of this DataSet to use the same TaxonSet. If
        `taxon_namespace` If `taxon_namespace` is None, then a new TaxonSet will be
        created, added to self.taxa, and that is the TaxonSet that will be
        attached.
        """
        if taxon_namespace is None:
            raise TypeError("Automatic creation of a new TaxonNamespace is no longer supported: `taxon_namespace` argument required to be passed a valid 'TaxonNamespace' instance")
            taxon_namespace = self.new_taxon_namespace()
        if taxon_namespace not in self.taxon_namespaces:
            self.add_taxon_namespace(taxon_namespace)
        self.attached_taxon_namespace = taxon_namespace
        return self.attached_taxon_namespace

    def detach_taxon_namespace(self):
        t = self.attached_taxon_namespace
        self.attached_taxon_namespace = None
        return t

    def _process_taxon_namespace_directives(self, kwargs_dict):
        """
        The following idioms are supported:

            `taxon_namespace=tns`
                Attach `tns` as the bound (single, unified) taxonomic namespace
                reference for all objects.
            `attached_taxon_namespace=tns`
                Attach `tns` as the bound (single, unified) taxonomic namespace
                reference for all objects.
            `attach_taxon_namespace=True, attached_taxon_namespace=tns`
                Attach `tns` as the bound (single, unified) taxonomic namespace
                reference for all objects.
            `attach_taxon_namespace=True`
                Create a *new* :class:`TaxonNamespace` and set it as the bound
                (single, unified) taxonomic namespace reference for all
                objects.
        """
        deprecated_kw = [
                "taxon_namespace",
                "attach_taxon_namespace",
                "attached_taxon_namespace",
                "taxon_set",
                "attach_taxon_set",
                "attached_taxon_set",
                ]
        for kw in deprecated_kw:
            if kw in kwargs_dict:
                raise TypeError("'{}' is no longer supported as a keyword argument to the constructor. Use the instance method 'attach_taxon_namespace()' instead".format(kw))
        taxon_namespace = None
        attach_taxon_namespace = False
        if ( ("taxon_set" in kwargs_dict or "taxon_namespace" in kwargs_dict)
                and ("attached_taxon_set" in kwargs_dict or "attached_taxon_namespace" in kwargs_dict)
                ):
            raise TypeError("Cannot specify both 'taxon_namespace'/'taxon_set' and 'attached_taxon_namespace'/'attached_taxon_set' together")
        if "taxon_set" in kwargs_dict:
            if "taxon_namespace" in kwargs_dict:
                raise TypeError("Both 'taxon_namespace' and 'taxon_set' cannot be specified simultaneously: use 'taxon_namespace' ('taxon_set' is only supported for legacy reasons)")
            kwargs_dict["taxon_namespace"] = kwargs_dict["taxon_set"]
            del kwargs_dict["taxon_set"]
        if "attached_taxon_set" in kwargs_dict:
            if "attached_taxon_namespace" in kwargs_dict:
                raise TypeError("Both 'attached_taxon_namespace' and 'attached_taxon_set' cannot be specified simultaneously: use 'attached_taxon_namespace' ('attached_taxon_set' is only supported for legacy reasons)")
            kwargs_dict["attached_taxon_namespace"] = kwargs_dict["attached_taxon_set"]
            del kwargs_dict["attached_taxon_set"]
        if "taxon_namespace" in kwargs_dict:
            taxon_namespace = kwargs_dict.pop("taxon_namespace", None)
            attach_taxon_namespace = True
        elif "attached_taxon_namespace" in kwargs_dict:
            taxon_namespace = kwargs_dict["attached_taxon_namespace"]
            if not isinstance(taxon_namespace, TaxonNamespace):
                raise TypeError("'attached_taxon_namespace' argument must be an instance of TaxonNamespace")
            attach_taxon_namespace = True
        else:
            taxon_namespace = None
            attach_taxon_namespace = kwargs_dict.get("attach_taxon_namespace", False)
        kwargs_dict.pop("taxon_namespace", None)
        kwargs_dict.pop("attach_taxon_namespace", None)
        kwargs_dict.pop("attached_taxon_namespace", None)
        if attach_taxon_namespace or (taxon_namespace is not None):
            self.attach_taxon_namespace(taxon_namespace)
        return taxon_namespace, attach_taxon_namespace

    ### **Legacy** ###

    def _get_taxon_sets(self):
        self.taxon_sets_deprecation_warning()
        return self.taxon_namespaces
    def _set_taxon_sets(self, v):
        self.taxon_sets_deprecation_warning()
        self.taxon_namespaces = v
    def _del_taxon_sets(self):
        self.taxon_sets_deprecation_warning()
    taxon_sets = property(_get_taxon_sets, _set_taxon_sets, _del_taxon_sets)

    def taxon_sets_deprecation_warning(self):
        pass
        # error.critical_deprecation_alert("`DataSet.taxon_sets` will no longer be supported in future releases; use `DataSet.taxon_namespaces` instead",
        #         stacklevel=4)

    def _get_attached_taxon_set(self):
        self.attached_taxon_set_deprecation_warning()
        return self.attached_taxon_namespace
    def _set_attached_taxon_set(self, v):
        self.attached_taxon_set_deprecation_warning()
        self.attached_taxon_namespace = v
    def _del_attached_taxon_set(self):
        self.attached_taxon_set_deprecation_warning()
    attached_taxon_set = property(_get_attached_taxon_set, _set_attached_taxon_set, _del_attached_taxon_set)

    def attached_taxon_set_deprecation_warning(self):
        pass
        # error.critical_deprecation_alert("`DataSet.attached_taxon_set` will no longer be supported in future releases; use `DataSet.attached_taxon_namespace` instead",
        #         stacklevel=4)

    def add_taxon_set(self, taxon_set):
        """
        DEPRECATED: Use `add_taxon_namespace()` instead.
        """
        return self.add_taxon_namespace(taxon_namespace=taxon_set)

    def new_taxon_set(self, *args, **kwargs):
        """
        DEPRECATED: Use `new_taxon_namespace()` instead.
        """
        return self.new_taxon_namespace(*args, **kwargs)

    def attach_taxon_set(self, taxon_set=None):
        """
        DEPRECATED: Use `attach_taxon_namespace()` instead.
        """
        return self.attach_taxon_namespace(taxon_namespace=taxon_set)

    def detach_taxon_set(self):
        """
        DEPRECATED: Use `detach_taxon_namespace()` instead.
        """
        self.detach_taxon_namespace()

    ### TreeList ###

    def add_tree_list(self, tree_list):
        """
        Adds a :class:`TreeList` instance to this dataset if it is not already
        there.

        Parameters
        ----------
        tree_list : :class:`TreeList`
            The :class:`TreeList` object to be added.
        """
        if tree_list.taxon_namespace not in self.taxon_namespaces:
            self.taxon_namespaces.add(tree_list.taxon_namespace)
        self.tree_lists.add(tree_list)
        return tree_list

    def new_tree_list(self, *args, **kwargs):
        """
        Creates a new :class:`TreeList` instance, adds it to this DataSet.

        Parameters
        ----------
        \*args : positional arguments
            Passed directly to :class:`TreeList` constructor.
        \*\*kwargs : keyword arguments, optional
            Passed directly to :class:`TreeList` constructor.

        Returns
        -------
        t : :class:`TreeList`
            The new :class:`TreeList` instance created.
        """
        if self.attached_taxon_namespace is not None:
            if "taxon_namespace" in kwargs and kwargs["taxon_namespace"] is not self.attached_taxon_namespace:
                raise TypeError("DataSet object is attached to TaxonNamespace {}, but 'taxon_namespace' argument specifies different TaxonNamespace {}" .format(
                    repr(self.attached_taxon_namespace), repr(kwargs["taxon_namespace"])))
            else:
                kwargs["taxon_namespace"] = self.attached_taxon_namespace
        tree_list = treemodel.TreeList(*args, **kwargs)
        return self.add_tree_list(tree_list)

    # def get_tree_list(self, **kwargs):
    #     """
    #     Returns a TreeList object specified by one (and exactly one) of the
    #     following keyword arguments:

    #         - ``label``
    #         - ``oid``

    #     Raises ``KeyError`` if no matching ``TreeList`` is found, unless
    #     ``ignore_error`` is set to ``True``.
    #     """
    #     if "label" in kwargs and "oid" in kwargs:
    #         raise TypeError("Cannot specify both 'label' and 'oid'")
    #     elif "label" in kwargs:
    #         for t in self.tree_lists:
    #             if t.label == kwargs['label']:
    #                 return t
    #         if not kwargs.get("ignore_error", False):
    #             raise KeyError(kwargs['label'])
    #     elif "oid" in kwargs:
    #         for t in self.tree_lists:
    #             if t.oid == kwargs['oid']:
    #                 return t
    #         if not kwargs.get("ignore_error", False):
    #             raise KeyError(kwargs['oid'])
    #     else:
    #         raise TypeError("Must specify one of: 'label' or 'oid'")

    ### CharacterMatrix ###

    def add_char_matrix(self, char_matrix):
        """
        Adds a :class:`CharacterMatrix` or :class:`CharacterMatrix`-derived
        instance to this dataset if it is not already there.

        Parameters
        ----------
        char_matrix : :class:`CharacterMatrix`
            The :class:`CharacterMatrix` object to be added.
        """
        if char_matrix.taxon_namespace not in self.taxon_namespaces:
            self.taxon_namespaces.add(char_matrix.taxon_namespace)
        self.char_matrices.add(char_matrix)
        return char_matrix

    def new_char_matrix(self, char_matrix_type, *args, **kwargs):
        """
        Creation and accession of new `CharacterMatrix` (of class
        `char_matrix_type`) into `chars` of self."
        """
        if self.attached_taxon_namespace is not None:
            if "taxon_namespace" in kwargs and kwargs["taxon_namespace"] is not self.attached_taxon_namespace:
                raise TypeError("DataSet object is attached to TaxonNamespace %s, but 'taxon_namespace' argument specifies different TaxonNamespace %s" % (
                    repr(self.attached_taxon_namespace), repr(kwargs["taxon_namespace"])))
            else:
                kwargs["taxon_namespace"] = self.attached_taxon_namespace
        if isinstance(char_matrix_type, str):
            char_matrix = charmatrixmodel.new_char_matrix(
                    data_type_name=char_matrix_type,
                    *args,
                    **kwargs)
        else:
            char_matrix = char_matrix_type(*args, **kwargs)
        return self.add_char_matrix(char_matrix)
