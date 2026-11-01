#define PY_SSIZE_T_CLEAN
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <Python.h>
#include <numpy/arrayobject.h>
#include <stdint.h>

/* All floating reductions remain the loaded NumPy dtype's dot callback.
 * No handwritten sum, changed stride, GIL release or retained work buffers. */
static int vector(PyObject *object, npy_intp length, int writable) {
    PyArrayObject *a;
    if (!PyArray_CheckExact(object)) goto invalid;
    a=(PyArrayObject *)object;
    if (PyArray_TYPE(a)!=NPY_DOUBLE || PyArray_NDIM(a)!=1 ||
        PyArray_DIM(a,0)!=length || PyArray_STRIDE(a,0)!=(npy_intp)sizeof(double) ||
        !PyArray_ISCARRAY_RO(a) || !PyArray_ISNOTSWAPPED(a) ||
        (writable && !PyArray_ISWRITEABLE(a))) goto invalid;
    return 1;
invalid:
    PyErr_SetString(PyExc_ValueError,"native100 requires exact contiguous native float64 buffers");
    return 0;
}

static int overlap(PyObject *a, PyObject *b) {
    PyArrayObject *x=(PyArrayObject *)a,*y=(PyArrayObject *)b;
    uintptr_t p=(uintptr_t)PyArray_DATA(x),q=(uintptr_t)PyArray_DATA(y);
    return p<q+(uintptr_t)PyArray_NBYTES(y) && q<p+(uintptr_t)PyArray_NBYTES(x);
}

static int separate(PyObject *a, PyObject *b) {
    if (!overlap(a,b)) return 1;
    PyErr_SetString(PyExc_ValueError,"native100 output overlaps input or another output");
    return 0;
}

static PyArray_DotFunc *dot_function(PyObject *object) {
    PyArray_Descr *dtype=PyArray_DESCR((PyArrayObject *)object);
    PyArray_DotFunc *dot;
#if NPY_ABI_VERSION >= 0x02000000
    dot=PyDataType_GetArrFuncs(dtype)->dotfunc;
#else
    dot=dtype->f->dotfunc;
#endif
    if (!dot) PyErr_SetString(PyExc_RuntimeError,"NumPy float64 dot callback unavailable");
    return dot;
}

static double *data(PyObject *object) { return (double *)PyArray_DATA((PyArrayObject *)object); }

static PyObject *quality_squares(PyObject *self, PyObject *args) {
    PyObject *x,*left,*right;
    PyArray_DotFunc *dot;
    double *v,*l,*r;
    int i;
    (void)self;
    if (!PyArg_ParseTuple(args,"OOO:quality_squares",&x,&left,&right)) return NULL;
    if (!vector(x,100,0) || !vector(left,30,1) || !vector(right,30,1) ||
        !separate(x,left) || !separate(x,right) || !separate(left,right)) return NULL;
    dot=dot_function(x);if (!dot) return NULL;
    v=data(x);l=data(left);r=data(right);
    for (i=0;i<30;++i) {
        npy_intp lag=i+8,length=100-lag;
        dot(v,sizeof(double),v,sizeof(double),l+i,length,NULL);
        dot(v+lag,sizeof(double),v+lag,sizeof(double),r+i,length,NULL);
    }
    Py_RETURN_NONE;
}

static PyObject *quality_numerators(PyObject *self, PyObject *args) {
    PyObject *x,*products,*output;
    PyArray_DotFunc *dot;
    double *v,*p,*n;
    int i;
    (void)self;
    if (!PyArg_ParseTuple(args,"OOO:quality_numerators",&x,&products,&output)) return NULL;
    if (!vector(x,100,0) || !vector(products,30,0) || !vector(output,30,1) ||
        !separate(x,output) || !separate(products,output)) return NULL;
    dot=dot_function(x);if (!dot) return NULL;
    v=data(x);p=data(products);n=data(output);
    for (i=0;i<30;++i) {
        n[i]=0.;
        if (p[i]>0.) dot(v,sizeof(double),v+i+8,sizeof(double),n+i,92-i,NULL);
    }
    Py_RETURN_NONE;
}

static int parts(PyObject *object, PyObject *output) {
    int i;
    if (!PyList_CheckExact(object) || PyList_GET_SIZE(object)!=11) {
        PyErr_SetString(PyExc_ValueError,"native100 history needs eleven lag-ordered arrays");return 0;
    }
    for (i=0;i<11;++i) {
        PyObject *part=PyList_GET_ITEM(object,i);
        npy_intp length=i<=5 ? 95+i : 105-i;
        if (!vector(part,length,0) || !separate(part,output)) return 0;
    }
    return 1;
}

static PyObject *norm_squares(PyObject *self, PyObject *args) {
    PyObject *values,*output;
    PyArray_DotFunc *dot;
    int i;
    (void)self;
    if (!PyArg_ParseTuple(args,"OO:norm_squares",&values,&output)) return NULL;
    if (!vector(output,11,1) || !parts(values,output)) return NULL;
    dot=dot_function(output);if (!dot) return NULL;
    for (i=0;i<11;++i) {
        PyArrayObject *part=(PyArrayObject *)PyList_GET_ITEM(values,i);
        dot(PyArray_DATA(part),sizeof(double),PyArray_DATA(part),sizeof(double),
            data(output)+i,PyArray_DIM(part,0),NULL);
    }
    Py_RETURN_NONE;
}

static PyObject *pair_numerators(PyObject *self, PyObject *args) {
    PyObject *left,*right,*denominators,*output;
    PyArray_DotFunc *dot;
    int i;
    (void)self;
    if (!PyArg_ParseTuple(args,"OOOO:pair_numerators",&left,&right,&denominators,&output)) return NULL;
    if (!vector(denominators,11,0) || !vector(output,11,1) ||
        !parts(left,output) || !parts(right,output) || !separate(denominators,output)) return NULL;
    dot=dot_function(output);if (!dot) return NULL;
    for (i=0;i<11;++i) {
        PyArrayObject *a=(PyArrayObject *)PyList_GET_ITEM(left,i);
        PyArrayObject *b=(PyArrayObject *)PyList_GET_ITEM(right,i);
        data(output)[i]=0.;
        if (data(denominators)[i]!=0.)
            dot(PyArray_DATA(a),sizeof(double),PyArray_DATA(b),sizeof(double),
                data(output)+i,PyArray_DIM(a,0),NULL);
    }
    Py_RETURN_NONE;
}

static PyObject *center_parts(PyObject *self, PyObject *args) {
    PyObject *input,*list=NULL,*squares=NULL,*slice=NULL,*part=NULL,*total=NULL;
    PyObject *mean=NULL,*centered=NULL,*length=NULL,*start=NULL,*stop=NULL,*answer=NULL;
    PyArrayObject *array;
    PyArray_DotFunc *dot;
    npy_intp dimension=11;
    int i;
    (void)self;
    if (!PyArg_ParseTuple(args,"O:center_parts",&input)) return NULL;
    if (!PyArray_CheckExact(input)) goto invalid;
    array=(PyArrayObject *)input;
    if (PyArray_TYPE(array)!=NPY_DOUBLE || PyArray_NDIM(array)!=1 || PyArray_DIM(array,0)!=100 ||
        !PyArray_ISALIGNED(array) || !PyArray_ISNOTSWAPPED(array)) goto invalid;
    dot=dot_function(input);if (!dot) return NULL;
    list=PyList_New(11);squares=PyArray_SimpleNew(1,&dimension,NPY_DOUBLE);
    if (!list || !squares) goto error;
    for (i=0;i<11;++i) {
        int lag=i-5;
        npy_intp count=lag<0 ? 100+lag : 100-lag;
        start=PyLong_FromLong(lag<0 ? 0 : lag);
        stop=PyLong_FromLong(lag<0 ? 100+lag : 100);
        if (!start || !stop) goto error;
        slice=PySlice_New(start,stop,NULL);Py_CLEAR(start);Py_CLEAR(stop);
        if (!slice) goto error;
        part=PyObject_GetItem(input,slice);Py_CLEAR(slice);
        if (!part) goto error;
        /* One-dimensional add.reduce axis=None and add.reduce axis=0 use
         * the same original view/stride. Divide/subtract stay NumPy objects. */
        total=PyArray_Sum((PyArrayObject *)part,0,NPY_DOUBLE,NULL);
        length=PyLong_FromSsize_t((Py_ssize_t)count);
        if (!total || !length) goto error;
        mean=PyNumber_TrueDivide(total,length);Py_CLEAR(total);Py_CLEAR(length);
        if (!mean) goto error;
        centered=PyNumber_Subtract(part,mean);Py_CLEAR(part);Py_CLEAR(mean);
        if (!centered) goto error;
        if (!vector(centered,count,0)) goto error;
        dot(PyArray_DATA((PyArrayObject *)centered),sizeof(double),
            PyArray_DATA((PyArrayObject *)centered),sizeof(double),data(squares)+i,count,NULL);
        PyList_SET_ITEM(list,i,centered);centered=NULL;
    }
    answer=PyTuple_Pack(2,list,squares);Py_DECREF(list);Py_DECREF(squares);
    return answer;
invalid:
    PyErr_SetString(PyExc_ValueError,"native100 centering requires an aligned native float64 vector100");
    return NULL;
error:
    Py_XDECREF(list);Py_XDECREF(squares);Py_XDECREF(slice);Py_XDECREF(part);Py_XDECREF(total);
    Py_XDECREF(mean);Py_XDECREF(centered);Py_XDECREF(length);Py_XDECREF(start);Py_XDECREF(stop);
    return NULL;
}

static PyMethodDef methods[]={
    {"quality_squares",quality_squares,METH_VARARGS,"100-point lag8..37 squared norms."},
    {"quality_numerators",quality_numerators,METH_VARARGS,"Positive-product quality cross dots."},
    {"norm_squares",norm_squares,METH_VARARGS,"Eleven centered lag-part squared norms."},
    {"pair_numerators",pair_numerators,METH_VARARGS,"Nonzero-denominator lag cross dots."},
    {"center_parts",center_parts,METH_VARARGS,"Original strided centering and squared norms for eleven lags."},
    {NULL,NULL,0,NULL}
};
static struct PyModuleDef definition={
    PyModuleDef_HEAD_INIT,"_v3b25_statistics_dot","Bounded100-point NumPy dtype-dot batches.",
    0,methods,NULL,NULL,NULL,NULL
};
PyMODINIT_FUNC PyInit__v3b25_statistics_dot(void) {
    PyObject *module;
    if (_import_array()<0) return NULL;
    module=PyModule_Create(&definition);if (!module) return NULL;
    if (PyModule_AddStringConstant(module,"implementation","numpy_dtype_dotfunc_100_v2")<0) {
        Py_DECREF(module);return NULL;
    }
    return module;
}
