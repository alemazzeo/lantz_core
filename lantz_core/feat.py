# -*- coding: utf-8 -*-
"""
    lantz.core.feat
    ~~~~~~~~~~~~~~~

    Implements Feat and DictFeat property-like classes with data handling,
    logging, timing, cache and notification.

    :copyright: 2018 by Lantz Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

import functools

from collections import defaultdict

from pimpmyclass.helpers import Config
from pimpmyclass.props import (LockProperty, GetSetCacheProperty, ReadOnceProperty, PreventUnnecessarySetProperty, TransformProperty,
                               StatsProperty, LogProperty, ObservableProperty, StorageProperty, InstanceConfigurableProperty)
from pimpmyclass.dictprops import DictObservableProperty

from .processors import (Processor, to_quantity_converter, to_magnitude_converter,
                         mapper_or_checker, reverse_mapper_or_checker, range_checker, MyRange)


class Feat(LockProperty, ObservableProperty, PreventUnnecessarySetProperty, ReadOnceProperty,
           GetSetCacheProperty, TransformProperty, LogProperty, StatsProperty):
    """Pimped Python property for interfacing with instruments. Can be used as
    a decorator.

    Processors can registered for each arguments to modify their values before
    they are passed to the body of the method. Two standard processors are
    defined: `values` and `units` and others can be given as callables in the
    `get_funcs` parameter.

    If a method contains multiple arguments, use the `item` method.

    Feat has the following nested behaviors:

    1. Feat: lantz specific modifiers: values, units, limits, procs, read_once)
    2. LockProperty: locks the parent drive (for multi-threading apps)
    3. ObservableProperty: emits a signal when the cached value has changed (via set/get)
    4. SetCacheProperty: prevents unnecessary set operations by comparing the value in the cache
    5. TransformProperty: transform values according to predefined rules.
    6. LogProperty: log get and set operations
    7. StatsProperty: record number of calls and timing stats for get/set/failed operations.
    8. Finally the actual getter or setter is called.

    Parameters
    ----------
    fget : callable
        getter function.
    fset : callable
        setter function.
    doc : str
        docstring, if missing fget or fset docstring will be used.
    values : tuple or set or dict
        A dictionary to map key to values.
        A set to restrict the values.
    units : str or Quantity
        That can be interpreted as units.
    limits : tuple
        Specify a range (start, stop, step) for numerical values
    get_funcs : iterable of callables
        Other callables to be applied to input arguments.
    set_funcs : iterable of callables
        Other callables to be applied to input arguments.
    read_once : bool
        Indicates that the value will be cached and used in all further get operations.

    """

    __original_doc__ = ''

    _storage_ns = 'feat'
    _storage_ns_init = lambda instance: defaultdict(dict)

    # These are feat modifiers.
    values = Config()
    units = Config()
    limits = Config()
    get_funcs = Config()
    set_funcs = Config()

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)

        # Each feat is registered in the Driver class under the _lantz_feats attribute.
        # This attribute hold the qualname of the Driver subclass in __lantz_driver_cls__

        # To allow Driver subclassing, _lantz_feats is duplicated
        # if the owner class of the property does not match the __lantz_driver_cls__ value.
        # In this way, each DriverSubclass._lantz_feats contains only the Feats of DriverSubclass
        # and parent classes but not childs.

        d = owner._lantz_feats

        if getattr(d, '__lantz_driver_cls__', None) != owner.__qualname__:
            d = d.__class__(**d)
            setattr(d, '__lantz_driver_cls__', owner.__qualname__)
            owner._lantz_feats = d

        owner._lantz_feats[name] = self

        self.rebuild()

    # Modifiers Accesors
    # Get/set from instance.Feat or Class.Feat

    def on_config_set(self, instance, key, value):
        """Rebuild get and set funcs based on modifiers and
        store the resulting funcs in the Class.Feat or instance.

        Parameters
        ----------
        instance : object
            (Default value = None)

        """
        super().on_config_set(instance, key, value)

        if key not in ('values', 'units', 'limits', 'get_funcs', 'set_funcs'):
            return

        self.rebuild(instance)

    def rebuild(self, instance=None):
        values = self.values_iget(instance)
        units = self.units_iget(instance)
        limits = self.limits_iget(instance)
        get_funcs = self.get_funcs_iget(instance)
        set_funcs = self.set_funcs_iget(instance)

        get_processors = Processor()
        set_processors = Processor()

        if units:
            get_processors.append(to_quantity_converter(units))
            set_processors.append(to_magnitude_converter(units))
        if values:
            get_processors.append(reverse_mapper_or_checker(values))
            set_processors.append(mapper_or_checker(values))
        if limits:
            if isinstance(limits[0], (list, tuple)):
                set_processors.append(range_checker(tuple(MyRange(*l) for l in limits)))
            else:
                set_processors.append(range_checker(MyRange(*limits)))

        if get_funcs:
            for func in get_funcs:
                if func is not None:
                    get_processors.append(Processor(func))

        if set_funcs:
            for func in set_funcs:
                if func is not None:
                    set_processors.append(Processor(func))

        self.post_get_iset(instance, reversed(get_processors))
        self.pre_set_iset(instance, set_processors)


class DictFeat(InstanceConfigurableProperty, DictObservableProperty):
    """Pimped Python key, value property for interfacing with instruments.

    Parameters
    ----------
    keys : set
        Restricts the valid keys.

    See Feat for other parameters.

    """

    _storage_ns = 'dictfeat'
    _storage_ns_init = lambda instance: defaultdict(dict)

    # These are feat modifiers.
    values = Config()
    units = Config()
    limits = Config()
    get_funcs = Config()
    set_funcs = Config()

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)

        # See Feat.__set_name__ for a description of this part

        d = owner._lantz_dictfeats

        if getattr(d, '__lantz_driver_cls__', None) != owner.__qualname__:
            d = d.__class__(**d)
            setattr(d, '__lantz_driver_cls__', owner.__qualname__)
            owner._lantz_dictfeats = d

        owner._lantz_dictfeats[name] = self

    def build_subproperty(self, key, fget, fset, instance=None):
        p = Feat(
            fget=fget,
            fset=fset,
            **dict(self.config_iter(instance))
        )
        return p

    def on_config_set(self, instance, key, value):
        """Rebuild get and set funcs based on modifiers and
        store the resulting funcs in the Class.Feat or instance.

        Parameters
        ----------
        instance : object
            (Default value = None)

        """
        super().on_config_set(instance, key, value)

        if key not in ('values', 'units', 'limits', 'get_funcs', 'set_funcs'):
            return

        for _, subprop in self._subproperties.items():
            setattr(subprop, key, value)


class FeatProxy:
    """Proxy object for Feat that allows to
    store instance specific modifiers.
    """

    def __init__(self, instance, feat):
        super().__setattr__('instance', instance)
        super().__setattr__('proxied', feat)

    @property
    def __doc__(self):
        return self.feat.__doc__

    def __getattr__(self, item):

        if item in self.proxied._config_keys:
            return self.proxied.config_get(self.instance, item)

        elif hasattr(self.proxied, item):
            out = getattr(self.proxied, item)
            if callable(out):
                return functools.partial(getattr(self.proxied, item), self.instance)
            return out

        raise AttributeError('Cannot get %s in %s. '
                             'Invalid Feat method, property or modifier', item, self.proxied.name)

    def __setattr__(self, item, value):

        if item not in self.proxied._config_keys:
            raise AttributeError('Cannot set %s in %s. '
                                 'Invalid Feat modifier', item, self.proxied.name)

        self.proxied.config_set(self.instance, item, value)


class DictFeatProxy:
    """Proxy object for DictFeat that allows to
    store instance specific modifiers.
    """

    def __init__(self, instance, dictfeat):
        super().__setattr__('instance', instance)
        super().__setattr__('proxied', dictfeat)

    @property
    def __doc__(self):
        return self.proxied.__doc__

    def __getattr__(self, item):

        if item in self.proxied._config_keys:
            return self.proxied.config_get(self.instance, item)

        elif hasattr(self.proxied, item):
            out = getattr(self.proxied, item)
            if callable(out):
                return functools.partial(getattr(self.proxied, item), self.instance)
            return out

        raise AttributeError('Cannot get %s in %s. '
                             'Invalid DictFeat method, property or modifier', item, self.proxied.name)

    def __setattr__(self, item, value):

        if item not in self.proxied._config_keys:
            raise AttributeError('Cannot set %s in %s. '
                                 'Invalid DictFeat modifier', item, self.proxied.name)

        self.proxied.config_set(self.instance, item, value)

    def __getitem__(self, item):
        return FeatProxy(self.instance, self.proxied.subproperty(self.instance, item))
