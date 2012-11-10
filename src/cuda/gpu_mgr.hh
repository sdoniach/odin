
/* Header file for gpu_mgr.cu, GPUScatter class */

class GPUScatter {
    
    // declare variables
    // in CPU memory
    int bpg;      // <-- defines the number of rotations
    int tpb;      // always = 512
    unsigned int nQ_size;

    int nQ;
    float* h_qx;    // size: nQ
    float* h_qy;    // size: nQ
    float* h_qz;    // size: nQ

    int nAtoms;
    float* h_rx;    // size: nAtoms
    float* h_ry;    // size: nAtoms
    float* h_rz;    // size: nAtoms
    float* h_id;    // size: nAtoms

    float* h_rand1; // size: nRotations
    float* h_rand2; // size: nRotations
    float* h_rand3; // size: nRotations

    float* h_outQ;  // size: nQ (OUTPUT)

    // on device
    float* d_qx;    // size: nQ
    float* d_qy;    // size: nQ
    float* d_qz;    // size: nQ

    float* d_rx;    // size: nAtoms
    float* d_ry;    // size: nAtoms
    float* d_rz;    // size: nAtoms
    float* d_id;    // size: nAtoms

    float* d_rand1; // size: nRotations
    float* d_rand2; // size: nRotations
    float* d_rand3; // size: nRotations

    float* d_outQ;  // size: nQ (OUTPUT)


public:
  /* By using the swig default names INPLACE_ARRAY1, DIM1 in the header
     file (these aren't the names in the implementation file), we're giving
     swig the info it needs to cast to and from numpy arrays.
     
     If instead the constructor line said
       GPUAdder(int* myarray, int length);

     We would need a line like this in the swig.i file
       %apply (int* ARGOUT_ARRAY1, int DIM1) {(int* myarray, int length)}
   */

  GPUScatter( int bpg_,      // <-- defines the number of rotations
            
            int nQ_,
            float* h_qx_,    // size: nQ
            float* h_qy_,    // size: nQ
            float* h_qz_,    // size: nQ

            int nAtoms_,
            float* h_rx_,    // size: nAtoms
            float* h_ry_,    // size: nAtoms
            float* h_rz_,    // size: nAtoms
            float* h_id_,    // size: nAtoms

            float* h_rand1_, // size: nRotations
            float* h_rand2_, // size: nRotations
            float* h_rand3_, // size: nRotations

            float* h_outQ_  // size: nQ (OUTPUT)
           );
  void run();                              // does operation inplace on the GPU
  void retreive();                         // gets results back from GPU
  ~GPUScatter();                             // destructor
};
