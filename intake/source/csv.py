from . import base
from .utils import reverse_format, pattern_to_glob, unique_string


# For brevity, this implementation just wraps the Dask dataframe
# implementation. Generally, plugins should not use Dask directly, as the
# base class provides the implementation for to_dask().
class CSVSource(base.DataSource):
    """Read CSV files into dataframes

    Prototype of sources reading dataframe data

    """
    name = 'csv'
    version = '0.0.1'
    container = 'dataframe'
    partition_access = True

    def __init__(self, urlpath, csv_kwargs=None, metadata=None,
                 storage_options=None):
        """
        Parameters
        ----------
        urlpath: str, location of data
            May be a local path, or remote path if including a protocol specifier
            such as ``'s3://'``. May include glob wildcards.
        csv_kwargs: dict
            Any further arguments to pass to Dask's read_csv (such as block size)
            or to the `CSV parser <https://pandas.pydata.org/pandas-docs/stable/generated/pandas.read_csv.html>`_
            in pandas (such as which columns to use, encoding, data-types)
        storage_options: dict
            Any parameters that need to be passed to the remote data backend,
            such as credentials.
        """
        self._urlpath = pattern_to_glob(urlpath)
        self._pattern = urlpath
        self._storage_options = storage_options
        self._csv_kwargs = csv_kwargs or {}
        self._dataframe = None

        super(CSVSource, self).__init__(metadata=metadata)

    def _get_filname_args(self, include_path_column):
        col = include_path_column

        args = []
        for f in self._dataframe[col].cat.categories:
            args.append(reverse_format(self._pattern, f))

        arg_dict = {}
        for k in args[0]:
            v = [arg[k] for arg in args]
            arg_dict[k] = self._dataframe[col].cat.rename_categories(v)

        return arg_dict

    def _get_schema(self):
        import dask.dataframe

        urlpath, *_ = self._get_cache(self._urlpath)

        if self._dataframe is None:
            include_path_column = unique_string() if (self._urlpath != self._pattern) else False

            self._dataframe = dask.dataframe.read_csv(
                urlpath, storage_options=self._storage_options,
                include_path_column=include_path_column,
                **self._csv_kwargs)

            if include_path_column:
                self._dataframe = self._dataframe.assign(
                    **self._get_filname_args(include_path_column))
                self._dataframe = self._dataframe.drop([include_path_column], axis=1)

        dtypes = self._dataframe._meta.dtypes.to_dict()
        dtypes = {n: str(t) for (n, t) in dtypes.items()}
        return base.Schema(datashape=None,
                           dtype=dtypes,
                           shape=(None, len(dtypes)),
                           npartitions=self._dataframe.npartitions,
                           extra_metadata={})

    def _get_partition(self, i):
        self._get_schema()
        return self._dataframe.get_partition(i).compute()

    def read(self):
        self._get_schema()
        return self._dataframe.compute()

    def to_dask(self):
        self._get_schema()
        return self._dataframe

    def _close(self):
        self._dataframe = None
